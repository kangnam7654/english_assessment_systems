"""Whole-video feature extraction with bounded buffering and streamed output."""

import platform
import subprocess
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from presentation_attitude.artifacts import (
    implementation_hashes,
    sha256,
    write_json_atomic,
    write_jsonl_row,
)
from presentation_attitude.data.preprocessing import DEFAULTS, iter_preprocess
from presentation_attitude.models.assets import get_models
from presentation_attitude.paths import workspace_root
from presentation_attitude.schema import PART_COUNTS, PARTS
from presentation_attitude.vision.landmarks import LandmarkExtractor
from presentation_attitude.vision.video import FFmpegVideoReader


def process_video(
    video,
    output,
    *,
    fps=5,
    window=3,
    models_dir=None,
    model_specs=None,
    max_frames=None,
    allowed_formats=None,
    max_pixels=None,
):
    """Extract v:0 from the beginning to decoder EOF into a new directory.

    Args:
        video: Local input video path; the source must remain unchanged.
        output: New directory for summary.json and sequence.jsonl.
        fps: FFmpeg sampling frequency, default 5 frames per second.
        window: Positive odd centered smoothing window, default 3.
        models_dir: Cached MediaPipe assets; omitted paths use workspace defaults.
        model_specs: JSON asset URLs/hashes used to verify or download the models.
        max_frames: Optional sample limit; exceeding it fails without truncation.
        allowed_formats: Optional comma-separated FFmpeg input format whitelist.
        max_pixels: Optional maximum decoded frame area.

    Returns:
        Completed summary with provenance, settings and feature-availability
        ratios. This entry point does not predict presentation attitude.

    Owns one FFmpeg process and one MediaPipe VIDEO session for this video;
    context managers release both on completion or failure. Output streams raw
    XYZ, normalized/smoothed XY, validity and timestamps without image files.
    Once output creation succeeds, processing failures record a failed summary
    and propagate; partial sequences are never advertised as complete.

    Raises:
        FileExistsError: The destination already exists.
        ValueError: The frame limit is invalid, no frames are decoded, or the source changes
            while processing.
        RuntimeError: The decoder or detector fails; the failed summary is retained.
    """
    video, output = Path(video).resolve(), Path(output).resolve()
    reader = FFmpegVideoReader(
        video, fps=fps, allowed_formats=allowed_formats, max_pixels=max_pixels
    )
    if max_frames is not None and (type(max_frames) is not int or max_frames < 1):
        raise ValueError("max_frames must be a positive integer")
    if type(window) is not int or window < 1 or window % 2 != 1:
        raise ValueError("window must be a positive odd integer")
    if output.exists():
        raise FileExistsError(f"Choose a new output directory: {output}")
    if models_dir is None or model_specs is None:
        root = workspace_root()
        models_dir = models_dir or root / ".local-data/presentation-attitude/models"
        model_specs = (
            model_specs or root / "presentation_attitude_assessment/configs/models.json"
        )
    models_dir, model_specs = Path(models_dir), Path(model_specs)
    source_stat = video.stat()
    source_hash = sha256(video)
    models = get_models(models_dir, model_specs)
    summary = {
        "schema_version": 1,
        "purpose": "whole_video_features_not_attitude_prediction",
        "status": "running",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "path": str(video),
            "sha256": source_hash,
            "bytes": source_stat.st_size,
        },
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": {
            name: version(name)
            for name in ("mediapipe", "numpy", "opencv-contrib-python")
        },
        "ffmpeg_version": subprocess.check_output(
            ["ffmpeg", "-version"], text=True
        ).splitlines()[0],
        "models": models,
        "model_specs_sha256": sha256(model_specs),
        "implementation_sha256": implementation_hashes(),
        "sample_fps": fps,
        "settings": {**DEFAULTS, "window": window},
        "running_mode": "VIDEO",
        "delegate": "CPU",
        "num_faces": 1,
        "num_hands": 2,
        "all_detection_presence_tracking_thresholds": 0.5,
        "video_input": "ffmpeg_rgb24_stdout_numpy",
        "saved_frames": False,
        "timestamp_semantics": "resampled grid from video start; not original frame PTS",
        "smoothing": "centered, segment-local, full window only; boundaries unchanged",
        "z_policy": "raw only; excluded from normalized and smoothed features",
        "part_order": list(PARTS),
        "landmark_counts": dict(PART_COUNTS),
        "mask_semantics": "valid is feature availability, not padding or an attitude label",
        "sampled_frames": 0,
        "valid_frame_counts": {p: 0 for p in PARTS},
        "detected_frame_counts": {"face": 0, "at_least_one_hand": 0, "two_hands": 0},
        "last_sample_timestamp_ms": None,
        "sequence_file": None,
    }
    output.mkdir(parents=True, exist_ok=False)
    partial = output / "sequence.jsonl.partial"
    try:
        write_json_atomic(output / "summary.json", summary)
        with (
            reader,
            LandmarkExtractor(models_dir) as extractor,
            partial.open("x") as stream,
        ):
            summary.update(
                width=reader.width, height=reader.height, ffmpeg_command=reader.command
            )

            def rows():
                """Decode sampled frames and yield MediaPipe observations in timestamp order.

                Yields:
                    Manifest records in file order.

                Raises:
                    ValueError: Video exceeds sampled frame limit; no partial prediction is made.
                """
                for index, rgb in enumerate(reader):
                    if max_frames is not None and index >= max_frames:
                        raise ValueError(
                            "Video exceeds sampled frame limit; no partial prediction is made"
                        )
                    yield extractor.detect(
                        rgb, index, round(index * 1000 / fps), index / fps
                    )

            for record in iter_preprocess(
                rows(), reader.width, reader.height, fps, config={"window": window}
            ):
                write_jsonl_row(stream, record)
                summary["sampled_frames"] += 1
                summary["last_sample_timestamp_ms"] = record["raw"][
                    "interval_timestamp_ms"
                ]
                for part in PARTS:
                    summary["valid_frame_counts"][part] += int(record["valid"][part])
                counts, raw = summary["detected_frame_counts"], record["raw"]
                counts["face"] += int(raw["face_present"])
                counts["at_least_one_hand"] += int(raw["hand_count"] > 0)
                counts["two_hands"] += int(raw["hand_count"] == 2)
                if summary["sampled_frames"] % 100 == 0:
                    stream.flush()
                    write_json_atomic(output / "summary.json", summary)
        if reader.frame_count != summary["sampled_frames"]:
            raise ValueError("Decoded and written frame counts differ")
        final_stat = video.stat()
        if (source_stat.st_size, source_stat.st_mtime_ns) != (
            final_stat.st_size,
            final_stat.st_mtime_ns,
        ):
            raise ValueError("Input video changed during processing")
        count = summary["sampled_frames"]
        summary.update(
            sequence_sha256=sha256(partial),
            sampled_coverage_seconds=count / fps,
            first_to_last_sample_seconds=(count - 1) / fps,
            detected_frame_ratios={
                p: n / count for p, n in summary["detected_frame_counts"].items()
            },
            valid_frame_ratios={
                p: n / count for p, n in summary["valid_frame_counts"].items()
            },
            has_valid_features=any(summary["valid_frame_counts"].values()),
        )
        partial.replace(output / "sequence.jsonl")
        summary.update(
            status="complete",
            sequence_file="sequence.jsonl",
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        write_json_atomic(output / "summary.json", summary)
    except BaseException as error:
        summary.update(
            status="failed",
            sequence_file=None,
            error={"type": type(error).__name__, "message": str(error)},
        )
        write_json_atomic(output / "summary.json", summary)
        raise
    return summary

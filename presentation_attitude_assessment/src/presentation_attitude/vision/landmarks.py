"""Sample videos and extract face and hand landmarks using MediaPipe."""

import math
import platform
import re
import subprocess
from contextlib import ExitStack
from datetime import datetime, timezone
from importlib.metadata import version

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

from presentation_attitude.artifacts import (
    implementation_hashes,
    read_json,
    sha256,
    write_json,
    write_jsonl_row,
)
from presentation_attitude.evaluation.diagnostics import summarize
from presentation_attitude.evaluation.visualization import contact_sheet
from presentation_attitude.models.assets import get_models
from presentation_attitude.vision.video import FFmpegVideoReader


def xyz(landmarks):
    """Convert MediaPipe landmark objects to serializable XYZ triples.

    Args:
        landmarks: MediaPipe landmark objects.

    Returns:
        List of [x, y, z] coordinates in detector order.
    """
    return [[point.x, point.y, point.z] for point in landmarks]


class LandmarkExtractor:
    """Own one MediaPipe VIDEO tracking session for one continuous video.

    Enter with a with block, call detect() in timestamp order, then close.
    Both detector tasks are loaded once on entry and reused for all frames;
    create a new session for another video or disconnected interval.
    """

    def __init__(self, model_dir):
        """Record model paths without opening detector tasks.

        Args:
            model_dir: Directory containing cached MediaPipe model assets.
        """
        self.model_dir = model_dir
        self.stack = ExitStack()

    def __enter__(self):
        """Load one face task and one hand task for this VIDEO tracking session.

        Returns:
            This initialized context-managed resource.
        """
        def base(kind):
            """Build MediaPipe base options for a cached detector asset.

            Args:
                kind: Model asset basename for the MediaPipe task.

            Returns:
                MediaPipe BaseOptions pointing to the requested cached task asset.
            """
            return BaseOptions(
                model_asset_path=str(self.model_dir / f"{kind}_landmarker.task"),
                delegate=BaseOptions.Delegate.CPU,
            )

        face_options = vision.FaceLandmarkerOptions(
            base_options=base("face"),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        hand_options = vision.HandLandmarkerOptions(
            base_options=base("hand"),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        try:
            self.face_task = self.stack.enter_context(
                vision.FaceLandmarker.create_from_options(face_options)
            )
            self.hand_task = self.stack.enter_context(
                vision.HandLandmarker.create_from_options(hand_options)
            )
        except BaseException:
            self.stack.close()
            raise
        return self

    def detect(self, rgb, index, timestamp_ms, source_seconds):
        """Return raw face/hand XYZ and detection metadata for one RGB frame.

        rgb is an RGB uint8 array (H, W, 3). timestamp_ms must increase within
        this session; index is the output frame index. source_seconds labels the
        sampling grid, not an exact source PTS. Missing detections use empty lists.
        Handedness is a detector label, not a persistent tracked-person identity.

        Args:
            rgb: RGB uint8 frame of shape (H, W, 3).
            index: Zero-based item or frame index.
            timestamp_ms: Strictly increasing MediaPipe timestamp in milliseconds.
            source_seconds: Time on the sampling grid, not an exact source PTS.

        Returns:
            Raw face/hand XYZ, handedness, presence flags, and sampling metadata.
        """
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        face = self.face_task.detect_for_video(image, timestamp_ms)
        hands = self.hand_task.detect_for_video(image, timestamp_ms)
        row = {
            "frame_index": index,
            "interval_timestamp_ms": timestamp_ms,
            "source_grid_seconds": source_seconds,
            "face_present": bool(face.face_landmarks),
            "face_landmarks": xyz(face.face_landmarks[0])
            if face.face_landmarks
            else [],
            "hand_count": len(hands.hand_landmarks),
            "hands": [
                {
                    "landmarks": xyz(points),
                    "handedness": handedness[0].category_name,
                    "handedness_score": handedness[0].score,
                }
                for points, handedness in zip(hands.hand_landmarks, hands.handedness)
            ],
        }
        return row

    def __exit__(self, *exc):
        """Close all detector tasks, including when frame processing fails.

        Args:
            *exc: Exception details supplied by the context manager protocol.

        Returns:
            Exception-suppression result returned by the owned ExitStack.
        """
        return self.stack.__exit__(*exc)


def audit_interval(interval, source, fps, model_dir, output, *, save_frames=False):
    """Extract one planned interval and optionally save sampled images.

    Args:
        interval: One planned video interval.
        source: Source video path or caller-owned input stream, as required by this
            operation.
        fps: Frames per second on the FFmpeg resampling grid.
        model_dir: Directory containing cached MediaPipe model assets.
        output: Destination directory or file for generated artifacts.
        save_frames: Whether to save sampled frame images for inspection.

    Returns:
        Interval summary with detection rates, timestamps, and source metadata.
    """
    destination = output / interval["id"]
    destination.mkdir(parents=True)
    frames_dir = destination / "frames"
    if save_frames:
        frames_dir.mkdir()
    expected_frames = max(1, math.ceil(interval["duration_seconds"] * fps))
    preview_indices = set(
        np.linspace(0, expected_frames - 1, min(5, expected_frames), dtype=int)
    )
    previews, seen_states = {}, set()
    reader = FFmpegVideoReader(
        source,
        fps=fps,
        start_seconds=interval["start_seconds"],
        duration_seconds=interval["duration_seconds"],
    )
    rows = []
    # Disjoint audit intervals start fresh tracking sessions.
    with reader, LandmarkExtractor(model_dir) as extractor:
        for index, rgb in enumerate(reader):
            row = extractor.detect(
                rgb,
                index,
                round(index * 1000 / fps),
                interval["start_seconds"] + index / fps,
            )
            rows.append(row)
            state = (row["face_present"], row["hand_count"])
            if index in preview_indices or state not in seen_states:
                previews[index] = rgb
                seen_states.add(state)
            if save_frames:
                frame_path = frames_dir / f"{index + 1:06d}.png"
                if not cv2.imwrite(
                    str(frame_path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                ):
                    raise OSError(f"Cannot save diagnostic frame: {frame_path}")
    metrics = summarize(rows)
    with (destination / "landmarks.jsonl").open("w") as stream:
        for row in rows:
            write_jsonl_row(stream, row)
    contact_sheet(previews, rows, destination / "contact_sheet.jpg")
    result = {
        **interval,
        **metrics,
        "ffmpeg_command": reader.command,
        "width": reader.width,
        "height": reader.height,
        "saved_frames": save_frames,
        "landmarks_file": f"{interval['id']}/landmarks.jsonl",
        "contact_sheet": f"{interval['id']}/contact_sheet.jpg",
    }
    write_json(destination / "summary.json", result)
    return result


def validate_plan(plan, inventory):
    """Reject invalid intervals or references absent from the source inventory.

    Args:
        plan: Audit plan describing the intervals to inspect.
        inventory: Source inventory used to validate the plan.

    Raises:
        ValueError: sample_fps must be finite and in (0, 1000]; At least one interval is
            required.
    """
    fps = plan["sample_fps"]
    if (
        not isinstance(fps, (int, float))
        or not math.isfinite(fps)
        or not 0 < fps <= 1000
    ):
        raise ValueError("sample_fps must be finite and in (0, 1000]")
    ids = set()
    if not plan["intervals"]:
        raise ValueError("At least one interval is required")
    for interval in plan["intervals"]:
        key = interval["id"]
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", key) or key in ids:
            raise ValueError(f"Invalid or duplicate interval id: {key}")
        ids.add(key)
        source = inventory[interval["file_name"]]
        start, duration = interval["start_seconds"], interval["duration_seconds"]
        if (
            not all(math.isfinite(v) for v in (start, duration))
            or start < 0
            or duration <= 0
        ):
            raise ValueError(f"Invalid interval: {key}")
        if start + duration > source["duration_seconds"] + 1e-6:
            raise ValueError(f"Interval exceeds video duration: {key}")


def run_audit(root, plan_path, inventory_path, output, models_dir, save_frames=False):
    """Validate a plan and write per-interval landmarks and diagnostic summaries.

    Args:
        root: Repository root used to resolve relative resource paths.
        plan_path: Path to the audit plan JSON.
        inventory_path: Path to the source inventory JSON.
        output: Destination directory or file for generated artifacts.
        models_dir: Directory containing cached MediaPipe model assets.
        save_frames: Whether to save sampled frame images for inspection.

    Raises:
        ValueError: Video hash mismatch: <value>.
        FileExistsError: Choose a new output directory: <value>.
    """
    plan = read_json(plan_path)
    inventory = {s["file_name"]: s for s in read_json(inventory_path)["samples"]}
    validate_plan(plan, inventory)
    used = {i["file_name"] for i in plan["intervals"]}
    for name in sorted(used):
        source = inventory[name]
        if sha256(root / source["local_path"]) != source["sha256"]:
            raise ValueError(f"Video hash mismatch: {name}")
    if output.exists():
        raise FileExistsError(f"Choose a new output directory: {output}")
    models = get_models(
        models_dir, root / "presentation_attitude_assessment/configs/models.json"
    )
    output.mkdir(parents=True)
    metadata = {
        "schema_version": 2,
        "purpose": "detector_availability_not_attitude_evaluation",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "packages": {
            name: version(name)
            for name in ("mediapipe", "numpy", "opencv-contrib-python")
        },
        "ffmpeg_version": subprocess.check_output(
            ["ffmpeg", "-version"], text=True
        ).splitlines()[0],
        "sample_fps": plan["sample_fps"],
        "running_mode": "VIDEO",
        "delegate": "CPU",
        "num_faces": 1,
        "num_hands": 2,
        "all_detection_presence_tracking_thresholds": 0.5,
        "custom_smoothing": False,
        "distance_normalization": False,
        "video_input": "ffmpeg_rgb24_stdout_numpy",
        "saved_frames": save_frames,
        "implementation_sha256": implementation_hashes(),
        "timestamp_semantics": "resampled grid; approximate source time, not original frame PTS",
        "models": models,
        "plan": plan,
        "source_sha256": {name: inventory[name]["sha256"] for name in sorted(used)},
        "intervals": [],
        "status": "running",
    }
    write_json(output / "summary.json", metadata)
    for interval in plan["intervals"]:
        result = audit_interval(
            interval,
            root / inventory[interval["file_name"]]["local_path"],
            plan["sample_fps"],
            models_dir,
            output,
            save_frames=save_frames,
        )
        metadata["intervals"].append(result)
        write_json(output / "summary.json", metadata)
        print(
            interval["id"],
            result["sampled_frames"],
            result["detected_frame_counts"],
            flush=True,
        )
    metadata["status"] = "complete"
    write_json(output / "summary.json", metadata)

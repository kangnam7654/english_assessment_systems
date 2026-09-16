"""Detection availability and sampled continuity; these are not attitude labels."""

from pathlib import Path

from presentation_attitude.artifacts import (
    implementation_hashes,
    iter_jsonl,
    read_json,
    write_json,
)
from presentation_attitude.artifacts import sha256 as digest
from presentation_attitude.schema import PARTS


def summarize(rows):
    """Count detected faces and hands across sampled frames.

    Args:
        rows: Ordered per-frame landmark records.

    Returns:
        Sample count and per-detector presence counts and ratios.

    Raises:
        ValueError: No sampled frames; cannot calculate detection rates.
    """
    if not rows:
        raise ValueError("No sampled frames; cannot calculate detection rates")
    counts = {
        "face": sum(r["face_present"] for r in rows),
        "at_least_one_hand": sum(r["hand_count"] > 0 for r in rows),
        "two_hands": sum(r["hand_count"] == 2 for r in rows),
        "face_and_at_least_one_hand": sum(
            r["face_present"] and r["hand_count"] > 0 for r in rows
        ),
    }
    return {
        "sampled_frames": len(rows),
        "detected_frame_counts": counts,
        "detected_frame_ratios": {k: v / len(rows) for k, v in counts.items()},
    }


def runs(mask, fps, segment_ids=None):
    """Count runs; sampled coverage is N/fps, not original-video visibility time.

    Args:
        mask: Boolean detection-validity observations.
        fps: Frames per second on the FFmpeg resampling grid.
        segment_ids: Optional continuity segment IDs that prevent runs spanning a gap.

    Returns:
        Run counts and durations measured on the resampled frame grid.

    Raises:
        ValueError: A nonempty mask and positive FPS are required; Segment length
            mismatch.
    """
    if not mask or fps <= 0:
        raise ValueError("A nonempty mask and positive FPS are required")
    if segment_ids is not None and len(segment_ids) != len(mask):
        raise ValueError("Segment length mismatch")
    groups = []
    for i, value in enumerate(mask):
        boundary = i == 0 or value != mask[i - 1]
        if value and segment_ids is not None and i:
            boundary |= segment_ids[i] != segment_ids[i - 1]
        if boundary:
            groups.append({"present": bool(value), "start_frame": i, "frames": 0})
        groups[-1]["frames"] += 1
    for group in groups:
        group["sampled_coverage_seconds"] = group["frames"] / fps
        group["first_to_last_sample_seconds"] = (group["frames"] - 1) / fps

    def longest(state):
        """Find the longest run with the requested detection state.

        Args:
            state: Boolean detection state whose longest run is requested.

        Returns:
            Maximum contiguous frame count for the requested boolean state, or zero.
        """
        return max((g["frames"] for g in groups if g["present"] == state), default=0)

    return {
        "present_frames": sum(mask),
        "total_frames": len(mask),
        "present_ratio": sum(mask) / len(mask),
        "longest_present_frames": longest(True),
        "longest_missing_frames": longest(False),
        "runs": groups,
    }


def report_continuity(audit_dir, processed_dir, output):
    """Compare raw and processed detection runs and persist continuity diagnostics.

    Args:
        audit_dir: Directory containing the completed landmark audit.
        processed_dir: Directory containing normalized and smoothed audit records.
        output: Destination directory or file for generated artifacts.

    Raises:
        ValueError: Both runs must be complete; Preprocessing belongs to another audit.
    """
    audit = read_json(audit_dir / "summary.json")
    processed = read_json(processed_dir / "summary.json")
    if audit["status"] != "complete" or processed["status"] != "complete":
        raise ValueError("Both runs must be complete")
    if processed["audit_summary_sha256"] != digest(audit_dir / "summary.json"):
        raise ValueError("Preprocessing belongs to another audit")
    fps = audit["sample_fps"]
    results = []
    for interval in audit["intervals"]:
        key = interval["id"]
        raw_path = audit_dir / interval["landmarks_file"]
        feature_path = processed_dir / f"{key}.jsonl"
        raw = list(iter_jsonl(raw_path))
        features = list(iter_jsonl(feature_path))
        if (
            len(raw) != interval["sampled_frames"]
            or [r["raw"] for r in features] != raw
        ):
            raise ValueError(f"Raw frames were lost or altered: {key}")
        masks = {
            "face": [r["face_present"] for r in raw],
            "any_hand": [r["hand_count"] > 0 for r in raw],
            "two_hands": [r["hand_count"] == 2 for r in raw],
            "face_and_any_hand": [
                r["face_present"] and r["hand_count"] > 0 for r in raw
            ],
        }
        results.append(
            {
                "id": key,
                "selection": interval.get("selection"),
                "start_seconds": interval["start_seconds"],
                "raw_sha256": digest(raw_path),
                "processed_sha256": digest(feature_path),
                "raw_detection": {p: runs(m, fps) for p, m in masks.items()},
                "valid_features": {
                    p: runs(
                        [r["valid"][p] for r in features],
                        fps,
                        [r["segment_id"][p] for r in features],
                    )
                    for p in PARTS
                },
            }
        )
    result = {
        "purpose": "sampled_continuity_not_attitude_or_whole_video_visibility",
        "sample_fps": fps,
        "raw_preserved_frames": sum(i["sampled_frames"] for i in audit["intervals"]),
        "audit_summary_sha256": digest(audit_dir / "summary.json"),
        "processed_summary_sha256": digest(processed_dir / "summary.json"),
        "implementation_sha256": digest(Path(__file__)),
        "implementation_files_sha256": implementation_hashes(),
        "semantics": "Runs never cross intervals. N/fps is sampled coverage; (N-1)/fps is sample timestamp span. Hand presence does not establish identity.",
        "intervals": results,
    }
    write_json(output, result, exclusive=True)

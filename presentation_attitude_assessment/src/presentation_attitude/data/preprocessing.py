"""Face-relative XY features with explicit missingness."""

import math
import re
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from presentation_attitude.artifacts import (
    implementation_hashes,
    iter_jsonl,
    read_json,
    write_json,
    write_jsonl_row,
)
from presentation_attitude.artifacts import sha256 as digest
from presentation_attitude.schema import PART_COUNTS, PARTS

DEFAULTS = {
    "window": 3,
    "handedness_min_score": 0.7,
    "minimum_face_scale_px": 1.0,
    "max_gap_in_frame_periods": 1.5,
    "anchor_jump_in_face_scales": 1.0,
    "anchor_scale_ratio_limit": 2.0,
    "hand_switch_margin_in_frame_diagonals": 0.02,
}


def _checked_points(value, count):
    """Accept only a finite landmark array with the expected coordinate shape.

    Args:
        value: Value to serialize or validate.
        count: Expected number of landmarks.

    Returns:
        Finite NumPy XYZ array of shape (count, 3).

    Raises:
        ValueError: Coordinates are not finite XYZ triples with shape (count, 3).
    """
    points = np.asarray(value, dtype=float)
    if points.shape != (count, 3) or not np.isfinite(points).all():
        raise ValueError(f"Expected {count} finite XYZ landmarks")
    return points


def _face_anchor(points, size, minimum_scale):
    """Compute a shared face center and scale in pixel coordinates.

    size is (width, height). The scale is sqrt(bbox_width * bbox_height),
    so face and hand XY share one distance correction despite image aspect
    ratio. Degenerate faces below minimum_scale return None.

    Args:
        points: Landmark coordinates in the order defined by MediaPipe.
        size: Frame dimensions as (width, height).
        minimum_scale: Smallest acceptable face scale in pixels.

    Returns:
        Face center, scale, and bounding-box metadata, or None for a degenerate face.
    """
    pixels = points[:, :2] * size
    lower, upper = pixels.min(axis=0), pixels.max(axis=0)
    extent = upper - lower
    scale = float(np.sqrt(extent.prod()))
    if scale < minimum_scale:
        return None
    return {
        "center_px": ((lower + upper) / 2).tolist(),
        "scale_px": scale,
        "bbox_xyxy_px": [*lower.tolist(), *upper.tolist()],
        "center_image_xy": (((lower + upper) / 2) / size).tolist(),
        "size_image_xy": (extent / size).tolist(),
    }


def _normalize_xy(points, size, anchor):
    """Center image-normalized XY on the face and divide by its pixel scale.

    Args:
        points: Landmark coordinates in the order defined by MediaPipe.
        size: Frame dimensions as (width, height).
        anchor: Face center and scale used for distance normalization.

    Returns:
        Face-centered XY coordinates divided by the pixel-space face scale.
    """
    return (points[:, :2] * size - anchor["center_px"]) / anchor["scale_px"]


def restore_xy(points, size, anchor):
    """Restore image-normalized XY using the current frame's original anchor.

    Args:
        points: Landmark coordinates in the order defined by MediaPipe.
        size: Frame dimensions as (width, height).
        anchor: Face center and scale used for distance normalization.

    Returns:
        XY coordinates restored to the image-normalized coordinate system.
    """
    return (np.asarray(points) * anchor["scale_px"] + anchor["center_px"]) / size


def _select_hands(hands, threshold):
    """Select confident left/right hand detections and report ambiguous assignments.

    Args:
        hands: Detected hand records with handedness confidence.
        threshold: Decision or confidence threshold.

    Returns:
        Selected hand slots and per-side rejection reasons.
    """
    slots, reasons = {}, {}
    for side in ("Left", "Right"):
        candidates = [(i, h) for i, h in enumerate(hands) if h["handedness"] == side]
        if not candidates:
            reasons[side] = "not_detected"
        elif len(candidates) != 1:
            reasons[side] = "duplicate_handedness"
        elif candidates[0][1]["handedness_score"] < threshold:
            reasons[side] = "low_handedness_score"
        else:
            i, hand = candidates[0]
            slots[side] = (i, _checked_points(hand["landmarks"], PART_COUNTS["Left"]))
            reasons[side] = None
    return slots, reasons


def _suspected_switches(current, previous, size, margin):
    """Conservative wrist proximity warning, not an anatomical hand tracker.

    Args:
        current: Current frame's per-hand landmark selection.
        previous: Previous frame's per-hand landmark selection.
        size: Frame dimensions as (width, height).
        margin: Distance margin for flagging a suspected left/right assignment switch.

    Returns:
        Set of handedness labels with a suspected assignment switch.
    """
    flagged = set()
    for side, (_, points) in current.items():
        other = "Right" if side == "Left" else "Left"
        if other not in previous:
            continue
        wrist = points[0, :2] * size
        other_distance = np.linalg.norm(wrist - previous[other])
        same_distance = (
            np.linalg.norm(wrist - previous[side]) if side in previous else math.inf
        )
        if (
            other_distance < 0.15 * np.linalg.norm(size)
            and other_distance + margin < same_distance
        ):
            flagged.update((side, other))
    return flagged


def _normalize_rows(rows, width, height, fps, *, config=None):
    """Validate the sampling grid and attach face-relative coordinates and continuity metadata.

    Args:
        rows: Ordered per-frame landmark records.
        width: Decoded frame width in pixels.
        height: Decoded frame height in pixels.
        fps: Frames per second on the FFmpeg resampling grid.
        config: Optional preprocessing overrides of the default settings.

    Yields:
        Validated records with normalized coordinates and continuity segments.

    Raises:
        ValueError: Sampling settings, timestamps, frame indices, or landmark coordinates
            violate the preprocessing contract.
    """
    settings = {**DEFAULTS, **(config or {})}
    window = settings["window"]
    if type(window) is not int or window < 1 or window % 2 != 1:
        raise ValueError("window must be a positive odd integer")
    if not all(math.isfinite(v) and v > 0 for v in (width, height, fps)):
        raise ValueError("Image dimensions and FPS must be positive and finite")
    size = np.array([width, height], dtype=float)
    previous_record, previous_wrists = None, {}
    last_timestamp, previous_anchor = None, None
    segment_counter = {p: -1 for p in PARTS}
    for row in rows:
        timestamp = row["interval_timestamp_ms"]
        if (
            not math.isfinite(timestamp)
            or timestamp < 0
            or (last_timestamp is not None and timestamp <= last_timestamp)
        ):
            raise ValueError(
                "Timestamps must be finite, nonnegative and strictly increasing"
            )
        if type(row["face_present"]) is not bool or len(row["face_landmarks"]) != (
            PART_COUNTS["face"] if row["face_present"] else 0
        ):
            raise ValueError("Face detection mask/coordinate mismatch")
        if row["hand_count"] != len(row["hands"]) or not 0 <= row["hand_count"] <= 2:
            raise ValueError("Hand count/coordinate mismatch")
        for hand in row["hands"]:
            _checked_points(hand["landmarks"], PART_COUNTS["Left"])
            if hand["handedness"] not in ("Left", "Right"):
                raise ValueError("Unknown handedness")
            score = hand["handedness_score"]
            if not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError("Invalid handedness score")
        discontinuity = bool(row.get("break_before", False)) or last_timestamp is None
        if last_timestamp is not None:
            discontinuity |= (
                timestamp - last_timestamp
                > settings["max_gap_in_frame_periods"] * 1000 / fps
            )
            discontinuity |= (
                row["frame_index"] != previous_record["raw"]["frame_index"] + 1
            )
        if discontinuity:
            previous_wrists, previous_anchor = {}, None
        face = (
            _checked_points(row["face_landmarks"], PART_COUNTS["face"])
            if row["face_present"]
            else None
        )
        anchor = (
            _face_anchor(face, size, settings["minimum_face_scale_px"])
            if face is not None
            else None
        )
        anchor_jump = False
        if anchor and previous_anchor:
            displacement = np.linalg.norm(
                np.array(anchor["center_px"]) - previous_anchor["center_px"]
            )
            ratio = anchor["scale_px"] / previous_anchor["scale_px"]
            anchor_jump = (
                displacement
                > settings["anchor_jump_in_face_scales"] * previous_anchor["scale_px"]
                or max(ratio, 1 / ratio) > settings["anchor_scale_ratio_limit"]
            )
        slots, reasons = _select_hands(row["hands"], settings["handedness_min_score"])
        switches = _suspected_switches(
            slots,
            previous_wrists,
            size,
            settings["hand_switch_margin_in_frame_diagonals"] * np.linalg.norm(size),
        )
        for side in switches:
            slots.pop(side, None)
            reasons[side] = "handedness_switch_suspected"
        # Only adjacent, accepted detections contribute to identity continuity.
        previous_wrists = {
            side: points[0, :2] * size for side, (_, points) in slots.items()
        }
        normalized = {part: None for part in PARTS}
        missing = {
            "face": "not_detected" if face is None else "degenerate_face_scale",
            **reasons,
        }
        if anchor:
            normalized["face"] = _normalize_xy(face, size, anchor).tolist()
            missing["face"] = None
            for side, (_, points) in slots.items():
                normalized[side] = _normalize_xy(points, size, anchor).tolist()
                missing[side] = None
        else:
            for side in slots:
                missing[side] = "face_anchor_unavailable"
        valid = {part: normalized[part] is not None for part in PARTS}
        segments = {}
        for part in PARTS:
            if valid[part]:
                if discontinuity or anchor_jump or not previous_record["valid"][part]:
                    segment_counter[part] += 1
                segments[part] = segment_counter[part]
            else:
                segments[part] = None
        record = {
            "raw": row,
            "anchor": anchor,
            "hand_source_index": {
                side: slots[side][0] if side in slots else None
                for side in ("Left", "Right")
            },
            "valid": valid,
            "missing_reason": missing,
            "hand_switch_suspected": sorted(switches),
            "break_before": discontinuity,
            "anchor_jump": bool(anchor_jump),
            "segment_id": segments,
            "normalized_xy": normalized,
            "smoothed_xy": {p: None for p in PARTS},
            "smoothing_support": {p: 0 for p in PARTS},
        }
        last_timestamp, previous_anchor = timestamp, anchor
        previous_record = record
        yield record
    if previous_record is None:
        raise ValueError("Empty extraction input")


def iter_preprocess(rows, width, height, fps, *, config=None):
    """Normalize detector rows and yield one feature record per input frame.

    Args:
        rows: Ordered MediaPipe records with XYZ, handedness and timestamps.
        width: Frame width in pixels.
        height: Frame height in pixels.
        fps: Sampling grid frequency, used for continuity checks.
        config: Optional overrides of DEFAULTS; window must be positive and odd.

    Records retain raw input and add normalized_xy, smoothed_xy, per-part
    validity, missing reasons and continuity segment IDs. Missing coordinates
    remain None. Z is preserved only in raw input. A centered moving average
    buffers at most one window and waits for window//2 future samples; EOF
    and each part's segment boundaries retain unsmoothed coordinates.
    Validation is lazy and runs while the returned iterator is consumed.

    Yields:
        One raw/normalized/smoothed feature record per sampled frame.
    """
    window = {**DEFAULTS, **(config or {})}["window"]
    # _normalize_rows validates settings before yielding the first record.
    buffer = deque()
    first_index, next_index = 0, 0

    def finish(index):
        """Finalize one buffered frame using only valid points from its continuity segment.

        Args:
            index: Zero-based item or frame index.

        Returns:
            Buffered feature record with centered smoothing applied where continuity
            permits.
        """
        offset = index - first_index
        record = buffer[offset]
        radius = window // 2
        for part in PARTS:
            if not record["valid"][part]:
                continue
            lo, hi = offset - radius, offset + radius + 1
            if (
                lo < 0
                or hi > len(buffer)
                or any(
                    buffer[j]["segment_id"][part] != record["segment_id"][part]
                    for j in range(max(0, lo), min(hi, len(buffer)))
                )
            ):
                lo, hi = offset, offset + 1
            points = [buffer[j]["normalized_xy"][part] for j in range(lo, hi)]
            record["smoothed_xy"][part] = np.mean(points, axis=0).tolist()
            record["smoothing_support"][part] = hi - lo
        return record

    for index, record in enumerate(
        _normalize_rows(rows, width, height, fps, config=config)
    ):
        buffer.append(record)
        if index >= window // 2:
            yield finish(next_index)
            next_index += 1
            if len(buffer) >= window:
                buffer.popleft()
                first_index += 1
    while next_index < first_index + len(buffer):
        yield finish(next_index)
        next_index += 1


def preprocess(rows, width, height, fps, *, config=None):
    """Materialize iter_preprocess() for small diagnostic intervals.

    Uses the identical normalization and smoothing rules. Whole-video callers
    should consume iter_preprocess() to avoid holding every record in memory.

    Args:
        rows: Ordered per-frame landmark records.
        width: Decoded frame width in pixels.
        height: Decoded frame height in pixels.
        fps: Frames per second on the FFmpeg resampling grid.
        config: Optional preprocessing overrides of the default settings.

    Returns:
        List of preprocessed feature records for the supplied interval.
    """
    return list(iter_preprocess(rows, width, height, fps, config=config))


def summarize(records):
    """Aggregate detection validity, movement, missing reasons, and smoothing diagnostics.

    Args:
        records: Preprocessed frame records to summarize.

    Returns:
        Per-part validity, missing-reason counts, segment counts, and movement
        diagnostics.
    """
    report = {
        "frames": len(records),
        "parts": {},
        "hand_switch_warning_frames": sum(
            bool(r["hand_switch_suspected"]) for r in records
        ),
        "anchor_jump_frames": sum(r["anchor_jump"] for r in records),
    }
    for part in PARTS:
        distances, accelerations = (
            {"normalized_xy": [], "smoothed_xy": []},
            {"normalized_xy": [], "smoothed_xy": []},
        )
        for i in range(1, len(records)):
            if records[i]["segment_id"][part] is None:
                continue
            if records[i - 1]["segment_id"][part] != records[i]["segment_id"][part]:
                continue
            for field in distances:
                current, previous = [
                    np.asarray(records[j][field][part]) for j in (i, i - 1)
                ]
                distances[field].append(
                    np.mean(np.sum((current - previous) ** 2, axis=1))
                )
                if (
                    i > 1
                    and records[i - 2]["segment_id"][part]
                    == records[i]["segment_id"][part]
                ):
                    older = np.asarray(records[i - 2][field][part])
                    accelerations[field].append(
                        np.mean(np.sum((current - 2 * previous + older) ** 2, axis=1))
                    )

        def rms(values):
            """Compute root-mean-square movement when observations are available.

            Args:
                values: Numeric observations used in the calculation.

            Returns:
                Root-mean-square value, or None when there are no observations.
            """
            return float(np.sqrt(np.mean(values))) if values else None

        report["parts"][part] = {
            "valid_frames": sum(r["valid"][part] for r in records),
            "missing_reasons": dict(
                Counter(
                    r["missing_reason"][part] for r in records if not r["valid"][part]
                )
            ),
            "support_histogram": dict(
                Counter(
                    r["smoothing_support"][part] for r in records if r["valid"][part]
                )
            ),
            "adjacent_pairs": len(distances["normalized_xy"]),
            "consecutive_triples": len(accelerations["normalized_xy"]),
            "step_rms_face_units": {k: rms(v) for k, v in distances.items()},
            "second_difference_rms_face_units": {
                k: rms(v) for k, v in accelerations.items()
            },
        }
    return report


def preprocess_audit(audit_dir, output, window=3):
    """Preprocess a completed interval audit into a new output directory.

    Reads landmark JSONL directly without decoding video or loading detectors.
    Legacy audits lacking dimensions use a saved PNG to recover frame size.
    Returns the summary also saved in summary.json. Existing output, invalid
    settings or incomplete source audits raise instead of being overwritten.

    Args:
        audit_dir: Directory containing the completed landmark audit.
        output: Destination directory or file for generated artifacts.
        window: Positive odd number of frames in the centered moving average.

    Raises:
        ValueError: Input audit is not complete; Invalid or duplicate interval id; No
            intervals.
        FileExistsError: Output must be a new directory.
    """
    audit = read_json(audit_dir / "summary.json")
    if audit.get("status") != "complete":
        raise ValueError("Input audit is not complete")
    if output.exists():
        raise FileExistsError("Output must be a new directory")
    # Validate all inputs before creating an output run.
    import cv2

    prepared, ids = [], set()
    for interval in audit["intervals"]:
        key = interval["id"]
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", key) or key in ids:
            raise ValueError("Invalid or duplicate interval id")
        ids.add(key)
        source = audit_dir / key / "landmarks.jsonl"
        rows = list(iter_jsonl(source))
        if len(rows) != interval["sampled_frames"]:
            raise ValueError(f"Frame count mismatch: {key}")
        if "width" in interval and "height" in interval:
            width, height = interval["width"], interval["height"]
        else:  # Historical PNG-based audits did not record image dimensions.
            frame = cv2.imread(str(audit_dir / key / "frames/000001.png"))
            if frame is None:
                raise ValueError(f"Missing historical frame dimensions: {key}")
            height, width = frame.shape[:2]
        records = preprocess(
            rows, width, height, audit["sample_fps"], config={"window": window}
        )
        prepared.append((key, source, records, width, height))
    if not prepared:
        raise ValueError("No intervals")
    output.mkdir(parents=True)
    summary = {
        "schema_version": 1,
        "purpose": "preprocessing_diagnostic_not_training_data",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "audit_summary_sha256": digest(audit_dir / "summary.json"),
        "implementation_sha256": digest(Path(__file__)),
        "implementation_files_sha256": implementation_hashes(),
        "numpy_version": np.__version__,
        "sample_fps": audit["sample_fps"],
        "settings": {**DEFAULTS, "window": window},
        "smoothing": "centered, segment-local, full window only; boundaries unchanged",
        "z_policy": "preserved only in raw; excluded from normalized and smoothed features",
        "status": "running",
        "intervals": [],
    }
    write_json(output / "summary.json", summary)
    for key, source, records, width, height in prepared:
        with (output / f"{key}.jsonl").open("w") as stream:
            for record in records:
                write_jsonl_row(stream, record)
        result = {
            "id": key,
            "source_sha256": digest(source),
            "width": width,
            "height": height,
            **summarize(records),
        }
        summary["intervals"].append(result)
        print(key, {p: result["parts"][p]["valid_frames"] for p in PARTS})
    summary["status"] = "complete"
    write_json(output / "summary.json", summary)

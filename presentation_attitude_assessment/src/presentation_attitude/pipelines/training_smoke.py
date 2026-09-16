"""Artificial coordinate fixtures test plumbing, not presentation attitudes."""

import hashlib
from pathlib import Path

import numpy as np

from presentation_attitude.artifacts import sha256, write_json, write_jsonl_row
from presentation_attitude.data.preprocessing import DEFAULTS
from presentation_attitude.pipelines.training import train
from presentation_attitude.schema import PART_COUNTS


def create_smoke_manifest(output, *, seed=42, test_only=False):
    """Write deterministic synthetic feature sequences and a matching split manifest.

    Args:
        output: Destination directory or file for generated artifacts.
        seed: Random seed for reproducible initialization or ordering.
        test_only: Whether to generate only a test split.

    Returns:
        Path to the newly written synthetic sample manifest.
    """
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    rng = np.random.default_rng(seed)
    samples = []
    for index in range(4 if test_only else 12):
        key = f"test_{seed}_{index:02d}" if test_only else f"fixture_{index:02d}"
        directory = output / key
        directory.mkdir()
        label, length = index % 2, 8 + index % 5 * 3
        valid_counts = {p: 0 for p in PART_COUNTS}
        with (directory / "sequence.jsonl").open("w") as stream:
            for frame in range(length):
                xy, valid = {}, {}
                for slot, (part, count) in enumerate(PART_COUNTS.items()):
                    valid[part] = not (
                        frame % 7 == 3 or (slot > 0 and (frame + slot) % 4 == 0)
                    )
                    # Arbitrary separable numerical patterns; no behavioral meaning.
                    coordinates = rng.normal((label * 2 - 1) * 0.1, 0.015, (count, 2))
                    xy[part] = coordinates.tolist() if valid[part] else None
                    valid_counts[part] += int(valid[part])
                record = {
                    "raw": {"frame_index": frame, "interval_timestamp_ms": frame * 200},
                    "smoothed_xy": xy,
                    "valid": valid,
                }
                write_jsonl_row(stream, record)
        summary = {
            "schema_version": 1,
            "purpose": "synthetic_test_sequence_not_mediapipe_output",
            "status": "complete",
            "sequence_file": "sequence.jsonl",
            "sequence_sha256": sha256(directory / "sequence.jsonl"),
            "sampled_frames": length,
            "sample_fps": 5,
            "settings": dict(DEFAULTS),
            "models": {"source": "synthetic_test_no_detector"},
            "z_policy": "raw only",
            "part_order": list(PART_COUNTS),
            "landmark_counts": PART_COUNTS,
            "valid_frame_counts": valid_counts,
            "source": {"sha256": hashlib.sha256(f"{seed}:{key}".encode()).hexdigest()},
        }
        write_json(directory / "summary.json", summary)
        samples.append(
            {
                "id": key,
                "sequence_dir": key,
                "label": label,
                "source_kind": "synthetic_test",
                "speaker_id": f"synthetic_speaker_{key}"
                if test_only
                else f"synthetic_speaker_{index}",
                "source_video_id": key,
                "split": "test"
                if test_only
                else ("train" if index < 8 else "validation"),
            }
        )
    manifest = output / "manifest.json"
    write_json(
        manifest, {"schema_version": 1, "purpose": "pipeline_smoke", "samples": samples}
    )
    return manifest


def run_smoke(output, *, epochs=3, seed=42):
    """Train on synthetic sequences to check the pipeline without claiming attitude accuracy.

    Args:
        output: Destination directory or file for generated artifacts.
        epochs: Number of complete training passes.
        seed: Random seed for reproducible initialization or ordering.

    Returns:
        Training summary for the synthetic pipeline check.
    """
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    manifest = create_smoke_manifest(output / "data", seed=seed)
    create_smoke_manifest(output / "test-data", seed=seed + 1, test_only=True)
    return train(manifest, output / "training", epochs=epochs, seed=seed)

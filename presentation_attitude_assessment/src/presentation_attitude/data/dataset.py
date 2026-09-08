"""Saved XY sequences -> tensors; no MediaPipe runtime is loaded for training."""

import math
from pathlib import Path

import torch
from torch.nn.utils.rnn import pad_sequence
from torch.utils.data import Dataset

from presentation_attitude.artifacts import iter_sequence, read_json, sha256
from presentation_attitude.schema import INPUT_SIZE, MASK_SIZE, PART_COUNTS


def load_features(directory, *, max_frames=10000):
    """Load one complete video as CPU tensors and its extraction summary.

    Returns:
        (features, timestamps_ms, summary), with float32 features (T, 1043)
        and int64 timestamps (T,). Columns are face/Left/Right flattened XY
        followed by three validity flags. Missing coordinates are zero-filled
        only at this tensor boundary; their validity flags remain zero.

    Raises:
        ValueError: Corrupt sequence, invalid coordinates/sampling grid, no
            usable features, or length outside [1, max_frames]. Videos are
            never silently truncated. File and metadata errors propagate.
    """
    directory = Path(directory)
    summary = read_json(directory / "summary.json")
    count = summary["sampled_frames"]
    if type(count) is not int or not 0 < count <= max_frames:
        raise ValueError(
            f"Sequence length must be in [1, {max_frames}]; no truncation is applied"
        )
    if (
        summary["part_order"] != list(PART_COUNTS)
        or summary["landmark_counts"] != PART_COUNTS
    ):
        raise ValueError("Unexpected landmark layout")
    fps = summary["sample_fps"]
    if not math.isfinite(fps) or not 0 < fps <= 1000:
        raise ValueError("Invalid sequence FPS")
    features = torch.zeros((count, INPUT_SIZE), dtype=torch.float32)
    timestamps = torch.empty(count, dtype=torch.int64)
    seen = 0
    for i, record in enumerate(iter_sequence(directory)):
        if i >= count:
            raise ValueError("Sequence exceeds declared frame count")
        timestamp = record["raw"]["interval_timestamp_ms"]
        if timestamp != round(i * 1000 / fps):
            raise ValueError("Expected a whole-video sampling grid")
        timestamps[i] = timestamp
        offset = 0
        for slot, (part, points) in enumerate(PART_COUNTS.items()):
            valid = record["valid"][part]
            if type(valid) is not bool:
                raise ValueError("Feature validity must be boolean")
            xy = record["smoothed_xy"][part]
            if valid:
                values = torch.tensor(xy, dtype=torch.float32)
                if values.shape != (points, 2) or not torch.isfinite(values).all():
                    raise ValueError(f"Invalid XY coordinates: {part}")
                features[i, offset : offset + points * 2] = values.flatten()
                features[i, -MASK_SIZE + slot] = 1
            elif xy is not None:
                raise ValueError("Unavailable coordinates must be null")
            offset += points * 2
        seen += 1
    if seen != count:
        raise ValueError("Sequence frame count mismatch")
    if not features[:, -MASK_SIZE:].any():
        raise ValueError("No usable features in this video")
    return features, timestamps, summary


class SequenceDataset(Dataset):
    """Load validated manifest samples lazily, one whole video per item.

    Pass the samples returned by read_manifest(). Each access rechecks the
    summary hash and sequence integrity; tensors are not cached. Items contain
    features, timestamps_ms, label and id for collate_sequences().
    """

    def __init__(self, samples, *, max_frames=10000):
        self.samples, self.max_frames = samples, max_frames

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, index):
        sample = self.samples[index]
        if sha256(sample["directory"] / "summary.json") != sample["summary_sha256"]:
            raise ValueError("Sequence metadata changed after manifest validation")
        features, timestamps, _ = load_features(
            sample["directory"], max_frames=self.max_frames
        )
        return {
            "features": features,
            "timestamps_ms": timestamps,
            "label": sample["label"],
            "id": sample["id"],
        }


def collate_sequences(samples):
    """Right-pad a nonempty list of video samples into a CPU batch.

    Returns features (B, T_max, 1043), int64 lengths (B,), float32 labels
    (B,), ids, timestamps_ms (B, T_max; padding=-1), and padding_mask
    (B, T_max; True means padding). The padding mask is distinct from the
    three per-frame feature validity flags. GRU packing uses lengths.
    """
    lengths = torch.tensor(
        [len(sample["features"]) for sample in samples], dtype=torch.int64
    )
    features = pad_sequence(
        [sample["features"] for sample in samples], batch_first=True
    )
    return {
        "features": features,
        "lengths": lengths,
        "padding_mask": torch.arange(features.shape[1])[None, :] >= lengths[:, None],
        "timestamps_ms": pad_sequence(
            [s["timestamps_ms"] for s in samples], batch_first=True, padding_value=-1
        ),
        "labels": torch.tensor([s["label"] for s in samples], dtype=torch.float32),
        "ids": [s["id"] for s in samples],
    }

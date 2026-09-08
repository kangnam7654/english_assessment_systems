"""Training sample provenance, eligibility and split validation."""

from pathlib import Path

from presentation_attitude.artifacts import read_json, sha256
from presentation_attitude.schema import feature_settings


def read_manifest(path, *, splits=("train", "validation"), require_both_classes=True):
    """Validate sample provenance and return (manifest, samples, settings).

    Sequence paths resolve relative to the manifest file. Returned sample
    copies include absolute directories and content hashes; no Torch or
    MediaPipe runtime is loaded. All sequences must be complete and share
    extraction settings. IDs/directories must be unique, and speaker/source
    identities cannot cross the requested splits.

    By default both binary classes are required in train and validation.
    For evaluation, pass splits=("test",) and require_both_classes=False.
    Invalid labels, eligibility or split provenance raise ValueError.
    """
    path = Path(path).resolve()
    manifest = read_json(path)
    purpose = manifest.get("purpose")
    if purpose not in ("pipeline_smoke", "attitude_training"):
        raise ValueError("Manifest purpose must be pipeline_smoke or attitude_training")
    samples = manifest["samples"]
    if not samples:
        raise ValueError("Empty training manifest")
    ids, directories, groups, labels = (
        set(),
        set(),
        {},
        {split: set() for split in splits},
    )
    settings = None
    result = []
    for sample in samples:
        sample = dict(sample)
        key, split, label = sample["id"], sample["split"], sample["label"]
        if not isinstance(key, str) or not key or key in ids:
            raise ValueError("Sample IDs must be nonempty and unique")
        ids.add(key)
        if split not in labels or type(label) is not int or label not in (0, 1):
            raise ValueError(f"Use {splits} splits and integer binary labels")
        if purpose == "pipeline_smoke":
            if sample.get("source_kind") != "synthetic_test":
                raise ValueError("Smoke data must be explicitly synthetic_test")
        elif (
            sample.get("source_kind") != "real"
            or sample.get("annotation_status") != "reviewed"
            or sample.get("training_eligible") is not True
        ):
            raise ValueError(
                "Real training requires reviewed labels and eligible real videos"
            )
        directory = (path.parent / sample["sequence_dir"]).resolve()
        if directory in directories:
            raise ValueError("Duplicate sequence directory")
        directories.add(directory)
        summary_path = directory / "summary.json"
        summary = read_json(summary_path)
        if summary["status"] != "complete":
            raise ValueError("Training requires completed sequences")
        expected_purpose = (
            "synthetic_test_sequence_not_mediapipe_output"
            if purpose == "pipeline_smoke"
            else "whole_video_features_not_attitude_prediction"
        )
        if summary.get("purpose") != expected_purpose:
            raise ValueError("Sequence purpose differs from the training manifest")
        current = feature_settings(summary)
        if settings is not None and current != settings:
            raise ValueError("Extraction settings differ across samples")
        settings = current
        for field, value in [
            ("speaker_id", sample["speaker_id"]),
            ("source_video_id", sample["source_video_id"]),
            ("source_sha256", summary["source"]["sha256"]),
        ]:
            if not isinstance(value, str) or not value:
                raise ValueError(f"Missing {field}")
            group = (field, value)
            if group in groups and groups[group] != split:
                raise ValueError(f"Train/validation leakage: {field}")
            groups[group] = split
        labels[split].add(label)
        result.append(
            {
                **sample,
                "directory": directory,
                "summary_sha256": sha256(summary_path),
                "source_sha256": summary["source"]["sha256"],
                "sequence_sha256": summary["sequence_sha256"],
            }
        )
    if require_both_classes and any(values != {0, 1} for values in labels.values()):
        raise ValueError(f"Each of {splits} requires both classes")
    return manifest, result, settings


def sample_provenance(samples):
    """Snapshot identities/content hashes without binding to filesystem locations."""
    fields = (
        "id",
        "split",
        "speaker_id",
        "source_video_id",
        "source_sha256",
        "sequence_sha256",
        "summary_sha256",
    )
    return [{key: sample[key] for key in fields} for sample in samples]

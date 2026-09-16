"""Evaluate a saved checkpoint on a disjoint, explicitly labeled test manifest."""

import math
from datetime import datetime, timezone
from pathlib import Path

import torch

from presentation_attitude.artifacts import (
    implementation_hashes,
    sha256,
    write_json_atomic,
    write_jsonl_row,
)
from presentation_attitude.data.manifest import read_manifest, sample_provenance
from presentation_attitude.evaluation.classification import binary_metrics
from presentation_attitude.models.runtime import ClassifierRuntime
from presentation_attitude.schema import label_mapping


def resolve_device(device):
    """Resolve auto to MPS when available, otherwise CPU.

    Args:
        device: PyTorch execution device, such as cpu, mps, or cuda.

    Returns:
        Explicit device string selected for model execution.

    Raises:
        ValueError: Evaluation device must be auto, cpu or mps; MPS is unavailable;
            choose --device cpu explicitly.
    """
    if device == "auto":
        return "mps" if torch.backends.mps.is_available() else "cpu"
    if device not in ("cpu", "mps"):
        raise ValueError("Evaluation device must be auto, cpu or mps")
    if device == "mps" and not torch.backends.mps.is_available():
        raise ValueError("MPS is unavailable; choose --device cpu explicitly")
    return device


def check_disjoint(training_samples, test_samples):
    """Reject shared identities or content between training and test samples.

    Args:
        training_samples: Validated Train/Validation provenance records.
        test_samples: Validated Test provenance records to check for overlap.

    Raises:
        ValueError: A speaker, source, sequence directory, or content hash occurs in both
            training/validation and test provenance.
    """
    for key in (
        "id",
        "directory",
        "speaker_id",
        "source_video_id",
        "source_sha256",
        "sequence_sha256",
    ):
        used = {sample[key] for sample in training_samples}
        if any(sample[key] in used for sample in test_samples):
            raise ValueError(f"Train/validation to test leakage: {key}")


def evaluate(
    checkpoint,
    manifest_path,
    training_manifest_path,
    output,
    *,
    threshold=0.5,
    device="auto",
    max_frames=10000,
):
    """Evaluate a checkpoint on an independent test manifest.

    checkpoint is paired with the training_manifest_path used to create it;
    manifest_path contains only test samples. Purposes, feature settings and
    provenance must match, and train/validation-to-test overlap is rejected.
    threshold determines class labels; ROC-AUC uses the raw model outputs.
    device="auto" selects MPS when available, otherwise CPU. max_frames rejects
    oversized videos without truncation.

    Returns the summary written to a new output directory alongside per-video
    predictions and misclassifications. Failed runs do not publish metrics.
    Synthetic results remain explicitly marked as pipeline checks.

    Args:
        checkpoint: Path to a trusted local PyTorch checkpoint.
        manifest_path: Path to the sample manifest used for this run.
        training_manifest_path: Manifest establishing the checkpoint's training
            provenance.
        output: Destination directory or file for generated artifacts.
        threshold: Decision or confidence threshold.
        device: PyTorch execution device, such as cpu, mps, or cuda.
        max_frames: Maximum frames per video; oversized sequences are rejected.

    Returns:
        Persisted evaluation summary with metrics and fixed-checkpoint provenance.

    Raises:
        ValueError: Checkpoint purpose, feature settings, data provenance, threshold, or
            frame limits do not satisfy the fixed-test evaluation contract.
        FileExistsError: The output directory already exists.
    """
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Threshold must be finite and in [0, 1]")
    if type(max_frames) is not int or max_frames < 1:
        raise ValueError("max_frames must be a positive integer")
    checkpoint, manifest_path, training_manifest_path, output = (
        Path(p).resolve()
        for p in (checkpoint, manifest_path, training_manifest_path, output)
    )
    if output.exists():
        raise FileExistsError("Choose a new evaluation output directory")
    runtime = ClassifierRuntime(checkpoint, device=resolve_device(device))
    manifest, samples, settings = read_manifest(
        manifest_path, splits=("test",), require_both_classes=False
    )
    training_manifest, training_samples, training_settings = read_manifest(
        training_manifest_path
    )
    if runtime.training_manifest_sha256 != sha256(training_manifest_path):
        raise ValueError("Training manifest does not match checkpoint")
    if (
        runtime.training_sample_provenance is not None
        and runtime.training_sample_provenance != sample_provenance(training_samples)
    ):
        raise ValueError("Training sample provenance changed since checkpoint creation")
    if not (runtime.purpose == manifest["purpose"] == training_manifest["purpose"]):
        raise ValueError("Checkpoint and manifest purposes differ")
    expected_mapping = label_mapping(runtime.purpose)
    if runtime.label_mapping != expected_mapping:
        raise ValueError("Checkpoint label mapping differs from purpose")
    if not (runtime.feature_settings == settings == training_settings):
        raise ValueError("Checkpoint and manifest feature settings differ")
    check_disjoint(training_samples, samples)
    report = {
        "schema_version": 1,
        "status": "running",
        "purpose": runtime.purpose,
        "evaluation_split": "test",
        "label_mapping": runtime.label_mapping,
        "positive_class": runtime.label_mapping["1"],
        "threshold": threshold,
        "device": str(runtime.device),
        "torch_version": str(torch.__version__),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "checkpoint_sha256": sha256(checkpoint),
        "manifest_sha256": sha256(manifest_path),
        "training_manifest_sha256": sha256(training_manifest_path),
        "provenance_basis": "checkpoint_snapshot"
        if runtime.training_sample_provenance is not None
        else "supplied_training_manifest_legacy_checkpoint",
        "sample_provenance": sample_provenance(samples),
        "implementation_sha256": implementation_hashes(),
        "notice": "Synthetic numeric patterns only; not attitude performance."
        if runtime.purpose == "pipeline_smoke"
        else "Results apply only to this labeled test set; not deployment validation or probability calibration.",
        "processed_samples": 0,
        "metrics": None,
        "predictions_file": None,
        "misclassifications_file": None,
    }
    output.mkdir(parents=True, exist_ok=False)
    labels, probabilities = [], []
    try:
        write_json_atomic(output / "summary.json", report)
        with (
            (output / "predictions.jsonl.partial").open("x") as predictions,
            (output / "misclassifications.jsonl.partial").open("x") as mistakes,
        ):
            for sample in samples:
                if (
                    sha256(sample["directory"] / "summary.json")
                    != sample["summary_sha256"]
                ):
                    raise ValueError("Test sequence metadata changed after validation")
                prediction = runtime.predict_sequence(
                    sample["directory"], max_frames=max_frames
                )
                probability = prediction["positive_class_probability"]
                if not math.isfinite(probability) or not 0 <= probability <= 1:
                    raise ValueError("Invalid prediction probability")
                predicted = int(probability >= threshold)
                record = {
                    "id": sample["id"],
                    "true_label": sample["label"],
                    "predicted_label": predicted,
                    "true_class": runtime.label_mapping[str(sample["label"])],
                    "predicted_class": runtime.label_mapping[str(predicted)],
                    "positive_class_probability": probability,
                    "frames": prediction["frames"],
                    "correct": predicted == sample["label"],
                }
                write_jsonl_row(predictions, record)
                if not record["correct"]:
                    write_jsonl_row(mistakes, record)
                labels.append(sample["label"])
                probabilities.append(probability)
                report["processed_samples"] += 1
        report["metrics"] = binary_metrics(labels, probabilities, threshold=threshold)
        for filename in ("predictions.jsonl", "misclassifications.jsonl"):
            (output / (filename + ".partial")).replace(output / filename)
        report.update(
            status="complete",
            predictions_file="predictions.jsonl",
            misclassifications_file="misclassifications.jsonl",
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        write_json_atomic(output / "summary.json", report)
    except BaseException as error:
        report.update(
            status="failed",
            metrics=None,
            predictions_file=None,
            misclassifications_file=None,
            error={"type": type(error).__name__, "message": str(error)},
        )
        write_json_atomic(output / "summary.json", report)
        raise
    return report

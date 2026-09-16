"""Train a small GRU from offline sequences, with explicit data provenance."""

import copy
import math
from datetime import datetime, timezone
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader

from presentation_attitude.artifacts import (
    implementation_hashes,
    sha256,
    write_json_atomic,
)
from presentation_attitude.data.dataset import SequenceDataset, collate_sequences
from presentation_attitude.data.manifest import read_manifest, sample_provenance
from presentation_attitude.models.gru import GRUClassifier
from presentation_attitude.models.runtime import ClassifierRuntime
from presentation_attitude.schema import FEATURE_SCHEMA, label_mapping


def _run_epoch(model, loader, loss_function, device, *, optimizer=None):
    """Run one train or validation pass, returning sample-weighted loss and steps.

    Args:
        model: Model used for the forward pass or parameter update.
        loader: Iterable of padded minibatches.
        loss_function: Loss callable applied to model outputs and targets.
        device: PyTorch execution device, such as cpu, mps, or cuda.
        optimizer: Optimizer to update parameters, or None for evaluation only.

    Returns:
        Sample-weighted epoch loss and number of optimizer steps.

    Raises:
        ValueError: Non-finite training or validation loss; An epoch requires at least
            one sample.
    """
    training = optimizer is not None
    model.train(training)
    total, count, steps = 0.0, 0, 0
    with torch.set_grad_enabled(training):
        for batch in loader:
            features = batch["features"].to(device)
            labels = batch["labels"].to(device)
            logits = model(features, batch["lengths"])
            loss = loss_function(logits, labels)
            if not torch.isfinite(loss):
                raise ValueError("Non-finite training or validation loss")
            if training:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                nn.utils.clip_grad_norm_(
                    model.parameters(), 1.0, error_if_nonfinite=True
                )
                optimizer.step()
                steps += 1
            total += loss.item() * len(labels)
            count += len(labels)
    if count == 0:
        raise ValueError("An epoch requires at least one sample")
    return total / count, steps


def train(
    manifest_path,
    output,
    *,
    epochs=3,
    batch_size=4,
    hidden_size=32,
    learning_rate=0.001,
    seed=42,
    device="cpu",
    max_frames=10000,
):
    """Train a GRU on offline sequences and return the persisted run summary.

    Args:
        manifest_path: Validated train/validation sample manifest path.
        output: New directory for summary.json and best.pt; never overwritten.
        epochs: Positive count of full training/validation passes.
        batch_size: Videos per padded batch.
        hidden_size: GRU hidden width.
        learning_rate: Positive finite Adam learning rate.
        seed: Torch model initialization and DataLoader shuffle seed.
        device: Torch execution device such as cpu or mps.
        max_frames: Per-video limit enforced without silent truncation.

    Saves the checkpoint with lowest validation loss, then verifies reloaded
    logits through ClassifierRuntime. No video decoding or landmark extraction
    occurs here. The routine sets Torch's seed and writes progress summaries;
    failures after output creation record status=failed and propagate.
    Synthetic smoke runs verify plumbing, not attitude classification quality.

    Returns:
        Persisted training summary for the Validation-selected checkpoint.

    Raises:
        ValueError: Epochs, batch size, hidden size and max frames must be positive
            integers; Learning rate must be finite and positive; No model parameters
            changed during training; Checkpoint reload changed validation logits.
        FileExistsError: Choose a new training output directory.
    """
    if any(
        type(v) is not int or v < 1
        for v in (epochs, batch_size, hidden_size, max_frames)
    ):
        raise ValueError(
            "Epochs, batch size, hidden size and max frames must be positive integers"
        )
    if not math.isfinite(learning_rate) or learning_rate <= 0:
        raise ValueError("Learning rate must be finite and positive")
    output, manifest_path = Path(output).resolve(), Path(manifest_path).resolve()
    if output.exists():
        raise FileExistsError("Choose a new training output directory")
    manifest, samples, settings = read_manifest(manifest_path)
    torch.manual_seed(seed)
    device = torch.device(device)
    model = GRUClassifier(hidden_size).to(device)
    initial = {
        name: value.detach().cpu().clone() for name, value in model.state_dict().items()
    }
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    loss_function = nn.BCEWithLogitsLoss()
    loaders = {
        split: DataLoader(
            SequenceDataset(
                [s for s in samples if s["split"] == split], max_frames=max_frames
            ),
            batch_size=batch_size,
            shuffle=split == "train",
            num_workers=0,
            generator=torch.Generator().manual_seed(seed),
            collate_fn=collate_sequences,
        )
        for split in ("train", "validation")
    }
    mapping = label_mapping(manifest["purpose"])
    report = {
        "status": "running",
        "purpose": manifest["purpose"],
        "label_mapping": mapping,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "torch_version": str(torch.__version__),
        "device": str(device),
        "feature_schema": FEATURE_SCHEMA,
        "feature_settings": settings,
        "model_config": model.config,
        "parameter_count": sum(p.numel() for p in model.parameters()),
        "manifest_sha256": sha256(manifest_path),
        "implementation_sha256": implementation_hashes(),
        "config": {
            "epochs": epochs,
            "batch_size": batch_size,
            "learning_rate": learning_rate,
            "seed": seed,
            "max_frames": max_frames,
        },
        "sample_counts": {
            split: len(loader.dataset) for split, loader in loaders.items()
        },
        "sample_provenance": [
            {"id": s["id"], "split": s["split"], "summary_sha256": s["summary_sha256"]}
            for s in samples
        ],
        "history": [],
        "optimizer_steps": 0,
        "classification_performance_verified": False,
    }
    output.mkdir(parents=True, exist_ok=False)
    best_loss, best_state = math.inf, None
    try:
        write_json_atomic(output / "summary.json", report)
        for epoch in range(1, epochs + 1):
            metrics = {"epoch": epoch}
            for split, loader in loaders.items():
                loss, steps = _run_epoch(
                    model,
                    loader,
                    loss_function,
                    device,
                    optimizer=optimizer if split == "train" else None,
                )
                metrics[split + "_loss"] = loss
                report["optimizer_steps"] += steps
            report["history"].append(metrics)
            if metrics["validation_loss"] < best_loss:
                best_loss = metrics["validation_loss"]
                best_state = copy.deepcopy(model.state_dict())
                report["best_epoch"] = epoch
                checkpoint = {
                    "schema_version": 1,
                    "purpose": manifest["purpose"],
                    "feature_schema": FEATURE_SCHEMA,
                    "feature_settings": settings,
                    "label_mapping": mapping,
                    "model_config": model.config,
                    "model_state_dict": best_state,
                    "epoch": epoch,
                    "manifest_sha256": report["manifest_sha256"],
                    "training_sample_provenance": sample_provenance(samples),
                }
                torch.save(checkpoint, output / "best.pt.partial")
                (output / "best.pt.partial").replace(output / "best.pt")
            write_json_atomic(output / "summary.json", report)
            print(
                f"epoch {epoch}: train={metrics['train_loss']:.6f} validation={metrics['validation_loss']:.6f}",
                flush=True,
            )
        report["parameters_changed"] = any(
            not torch.equal(value.detach().cpu(), initial[name])
            for name, value in model.state_dict().items()
        )
        if not report["parameters_changed"]:
            raise ValueError("No model parameters changed during training")
        # Compare the trained best state to its persisted and reloaded counterpart.
        model.load_state_dict(best_state)
        model.eval()
        runtime = ClassifierRuntime(output / "best.pt", device=str(device))
        batch = next(iter(loaders["validation"]))
        with torch.inference_mode():
            inputs = batch["features"].to(device)
            expected = model(inputs, batch["lengths"])
            restored = runtime.predict_logits(inputs, batch["lengths"])
        if not torch.equal(expected, restored):
            raise ValueError("Checkpoint reload changed validation logits")
        report.update(
            status="complete",
            checkpoint="best.pt",
            checkpoint_sha256=sha256(output / "best.pt"),
            checkpoint_reload_logits_identical=True,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        write_json_atomic(output / "summary.json", report)
    except BaseException as error:
        report.update(
            status="failed", error={"type": type(error).__name__, "message": str(error)}
        )
        write_json_atomic(output / "summary.json", report)
        raise
    return report

"""Native NeMo Parakeet experiment; Validation only, explicit optimizer and TDT loss."""

import argparse
import hashlib
import io
import json
import os
import random
import re
import time
import zipfile
from pathlib import Path

import jiwer
import numpy as np
import soundfile as sf
import torch
from huggingface_hub import hf_hub_download
from nemo.collections.asr.losses.rnnt import RNNTLoss
from nemo.collections.asr.models import ASRModel
from omegaconf import OmegaConf

from child_speech.paths import REPO_DIR

REPO = REPO_DIR
ROOT = Path(os.environ.get("ASR_RUN_DIR", REPO / ".local-data/asr-nemo"))
DATA = Path(os.environ.get("ASR_DATA_DIR", REPO / ".local-data/aihub541"))
ROOT.mkdir(parents=True, exist_ok=True)
SEED = 20260912
REV = "ae9ad07059c7c739ffaf932226a8fe64ae2620b0"
torch.backends.cuda.matmul.allow_tf32 = False
torch.backends.cudnn.allow_tf32 = False


def dump(path, obj):
    """Write JSON through a sibling temporary file, then replace the target.

    Args:
        path: Filesystem path to the input or output artifact.
        obj: JSON-serializable object to persist.
    """
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
    temp.replace(path)


def rows(split):
    """Read one AI Hub split manifest into memory.

    Args:
        split: Manifest split name, such as train, validation, or test.

    Returns:
        Manifest records in file order.
    """
    return [
        json.loads(s) for s in (DATA / f"splits/{split}.jsonl").read_text().splitlines()
    ]


def norm(s):
    """Normalize case, apostrophes, punctuation, and whitespace for WER/CER.

    Args:
        s: Transcript to normalize for error-rate comparison.

    Returns:
        Lowercase transcript with normalized punctuation and whitespace.
    """
    return " ".join(re.sub(r"[^a-z0-9'\s]", " ", s.lower().replace("’", "'")).split())


def load():
    """Restore the pinned cached Parakeet model on CUDA with the recorded TDT recipe.

    Returns:
        CUDA NeMo Parakeet model configured for the recorded experiment.
    """
    path = hf_hub_download(
        "nvidia/parakeet-tdt-0.6b-v2",
        "parakeet-tdt-0.6b-v2.nemo",
        revision=REV,
        local_files_only=True,
    )
    model = ASRModel.restore_from(path, map_location="cpu").cuda()
    model.spec_augmentation = None
    model.preprocessor.featurizer.dither = 0.0
    model.joint.set_fuse_loss_wer(False)
    model.loss = RNNTLoss(
        num_classes=1024,
        reduction="mean",
        loss_name="tdt",
        loss_kwargs={
            "durations": [0, 1, 2, 3, 4],
            "sigma": 0.0,
            "omega": 0.0,
            "fastemit_lambda": 0.0,
            "clamp": -1.0,
        },
    )
    # Preserve native NeMo dropout; recorded as a framework/recipe difference.
    return model


class Audio:
    """Read mono speech directly from the AI Hub ZIP without extracting WAV files."""
    def __init__(self):
        """Open the experiment audio ZIP for reuse across minibatches."""
        self.z = zipfile.ZipFile(DATA / "VS_eng_free_01.zip")

    def read(self, row):
        """Decode one archive member as a float32 16 kHz mono waveform.

        Args:
            row: Manifest record identifying an audio archive member and its transcript.

        Returns:
            One-dimensional float32 waveform at 16 kHz.

        Raises:
            AssertionError: The decoded audio is not mono at 16 kHz.
        """
        a, sr = sf.read(io.BytesIO(self.z.read(row["audio_member"])), dtype="float32")
        assert sr == 16000 and a.ndim == 1
        return a

    def batch(self, model, rs):
        """Pad CUDA waveforms and tokenizer targets for a NeMo TDT minibatch.

        Args:
            model: Model used for the forward pass or parameter update.
            rs: Manifest records to load in the supplied order.

        Returns:
            CUDA signal (B, S), signal lengths (B,), padded token IDs (B, U), and token
            lengths (B,).

        Raises:
            AssertionError: Audio format validation fails or a transcript tokenizes to zero tokens.
        """
        wavs = [torch.from_numpy(self.read(r)) for r in rs]
        lens = torch.tensor([w.numel() for w in wavs], device="cuda")
        tokens = [
            torch.tensor(model.tokenizer.text_to_ids(r["text"]), dtype=torch.long)
            for r in rs
        ]
        target_lens = torch.tensor([t.numel() for t in tokens], device="cuda")
        assert (target_lens > 0).all()
        return (
            torch.nn.utils.rnn.pad_sequence(wavs, batch_first=True).cuda(),
            lens,
            torch.nn.utils.rnn.pad_sequence(
                tokens, batch_first=True, padding_value=1024
            ).cuda(),
            target_lens,
        )


def loss(model, batch):
    """Compute the native NeMo TDT loss from a padded audio/text minibatch.

    Args:
        model: Model used for the forward pass or parameter update.
        batch: Padded inputs and lengths for the current minibatch.

    Returns:
        Differentiable scalar TDT loss for the minibatch.
    """
    signal, lens, target, tlens = batch
    encoded, elens = model(input_signal=signal, input_signal_length=lens)
    decoded, dlens, _ = model.decoder(targets=target, target_length=tlens)
    joint = model.joint(encoder_outputs=encoded, decoder_outputs=decoded)
    return model.loss(
        log_probs=joint, targets=target, input_lengths=elens, target_lengths=dlens
    )


def trainmode(model):
    """Enable training while keeping BatchNorm running statistics frozen.

    Args:
        model: Model used for the forward pass or parameter update.
    """
    model.train()
    for m in model.modules():
        if isinstance(m, torch.nn.BatchNorm1d):
            m.eval()


def optimizer(model):
    """Create AdamW with the recorded baseline learning rate and no weight decay.

    Args:
        model: Model used for the forward pass or parameter update.

    Returns:
        AdamW optimizer over the model parameters.
    """
    return torch.optim.AdamW(
        model.parameters(),
        lr=1e-5,
        betas=(0.9, 0.999),
        eps=1e-8,
        weight_decay=0,
        foreach=False,
    )


def ordered():
    """Validate the recorded Train manifest hash and deterministically shuffle its rows.

    Returns:
        Deterministically shuffled Train records after count/hash verification.

    Raises:
        AssertionError: Train does not contain 41,183 records or its hash differs from the
            recorded experiment protocol.
    """
    rs = rows("train")
    random.Random(SEED).shuffle(rs)
    assert len(rs) == 41183
    expected = json.loads(
        (REPO / "child_speech_recognition/results/protocol.json").read_text()
    )["manifest_hashes"]["train"]
    assert (
        hashlib.sha256((DATA / "splits/train.jsonl").read_bytes()).hexdigest()
        == expected
    ), "Train manifest differs from the recorded experiment"
    return rs

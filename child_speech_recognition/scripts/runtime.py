"""Native NeMo Parakeet experiment; Validation only, explicit optimizer and TDT loss."""

import argparse, hashlib, io, json, os, random, re, time, zipfile
from pathlib import Path
import numpy as np
import soundfile as sf
import torch
import jiwer
from huggingface_hub import hf_hub_download
from omegaconf import OmegaConf
from nemo.collections.asr.models import ASRModel
from nemo.collections.asr.losses.rnnt import RNNTLoss

REPO = Path(__file__).resolve().parents[2]
ROOT = Path(os.environ.get("ASR_RUN_DIR", REPO / ".local-data/asr-nemo"))
DATA = Path(os.environ.get("ASR_DATA_DIR", REPO / ".local-data/aihub541"))
ROOT.mkdir(parents=True, exist_ok=True)
SEED = 20260912
REV = "ae9ad07059c7c739ffaf932226a8fe64ae2620b0"
torch.backends.cuda.matmul.allow_tf32 = False
torch.backends.cudnn.allow_tf32 = False


def dump(path, obj):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
    temp.replace(path)


def rows(split):
    return [
        json.loads(s) for s in (DATA / f"splits/{split}.jsonl").read_text().splitlines()
    ]


def norm(s):
    return " ".join(re.sub(r"[^a-z0-9'\s]", " ", s.lower().replace("’", "'")).split())


def load():
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
    def __init__(self):
        self.z = zipfile.ZipFile(DATA / "VS_eng_free_01.zip")

    def read(self, row):
        a, sr = sf.read(io.BytesIO(self.z.read(row["audio_member"])), dtype="float32")
        assert sr == 16000 and a.ndim == 1
        return a

    def batch(self, model, rs):
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
    signal, lens, target, tlens = batch
    encoded, elens = model(input_signal=signal, input_signal_length=lens)
    decoded, dlens, _ = model.decoder(targets=target, target_length=tlens)
    joint = model.joint(encoder_outputs=encoded, decoder_outputs=decoded)
    return model.loss(
        log_probs=joint, targets=target, input_lengths=elens, target_lengths=dlens
    )


def trainmode(model):
    model.train()
    for m in model.modules():
        if isinstance(m, torch.nn.BatchNorm1d):
            m.eval()


def optimizer(model):
    return torch.optim.AdamW(
        model.parameters(),
        lr=1e-5,
        betas=(0.9, 0.999),
        eps=1e-8,
        weight_decay=0,
        foreach=False,
    )


def ordered():
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

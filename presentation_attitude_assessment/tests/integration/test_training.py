import json
import tempfile
import unittest
from pathlib import Path

import torch

from presentation_attitude.artifacts import sha256, write_json
from presentation_attitude.data.dataset import (
    SequenceDataset,
    collate_sequences,
    load_features,
)
from presentation_attitude.data.manifest import read_manifest
from presentation_attitude.models.runtime import ClassifierRuntime
from presentation_attitude.pipelines.training import train
from presentation_attitude.pipelines.training_smoke import create_smoke_manifest
from presentation_attitude.schema import INPUT_SIZE


class TrainingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.manifest = create_smoke_manifest(self.root / "data")

    def test_training_checkpoint_and_reused_runtime(self):
        report = train(self.manifest, self.root / "run", epochs=2, hidden_size=8)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["purpose"], "pipeline_smoke")
        self.assertEqual(report["optimizer_steps"], 4)
        self.assertTrue(report["parameters_changed"])
        self.assertTrue(report["checkpoint_reload_logits_identical"])
        runtime = ClassifierRuntime(self.root / "run/best.pt")
        before = runtime.predict_sequence(self.root / "data/fixture_08")
        runtime.predict_sequence(self.root / "data/fixture_09")
        after = runtime.predict_sequence(self.root / "data/fixture_08")
        self.assertEqual(before, after)
        self.assertTrue(0 <= before["positive_class_probability"] <= 1)
        self.assertEqual(before["label_mapping"]["1"], "test_pattern_b")

        # The public batch entry point must agree with saved-sequence inference,
        # ignore right padding, and never build a training graph.
        _, samples, _ = read_manifest(self.manifest)
        dataset = SequenceDataset(samples[8:10])
        batch = collate_sequences([dataset[0], dataset[1]])
        batch["features"].requires_grad_(True)
        logits = runtime.predict_logits(batch["features"], batch["lengths"])
        self.assertEqual(logits.shape, (2,))
        self.assertFalse(logits.requires_grad)
        expected = torch.tensor(
            [
                runtime.predict_sequence(sample["directory"])[
                    "positive_class_probability"
                ]
                for sample in samples[8:10]
            ]
        )
        torch.testing.assert_close(logits.sigmoid(), expected)
        padded = torch.nn.functional.pad(batch["features"], (0, 0, 0, 4), value=99)
        torch.testing.assert_close(
            runtime.predict_logits(padded, batch["lengths"]), logits
        )

    def test_coordinates_masks_lengths_and_frame_limit(self):
        features, timestamps, _ = load_features(self.root / "data/fixture_00")
        self.assertEqual(features.shape, (8, INPUT_SIZE))
        self.assertEqual(timestamps.tolist(), list(range(0, 1600, 200)))
        self.assertTrue(torch.equal(features[3], torch.zeros(INPUT_SIZE)))
        self.assertEqual(features[0, -3:].tolist(), [1, 1, 1])
        with self.assertRaisesRegex(ValueError, "no truncation"):
            load_features(self.root / "data/fixture_00", max_frames=2)

    def test_split_leakage_is_rejected_for_speaker_source_and_content(self):
        original = json.loads(self.manifest.read_text())
        for field in ("speaker_id", "source_video_id"):
            manifest = json.loads(json.dumps(original))
            manifest["samples"][8][field] = manifest["samples"][0][field]
            write_json(self.manifest, manifest)
            with (
                self.subTest(field=field),
                self.assertRaisesRegex(ValueError, "leakage"),
            ):
                read_manifest(self.manifest)
        write_json(self.manifest, original)
        first = json.loads((self.root / "data/fixture_00/summary.json").read_text())
        target = self.root / "data/fixture_08/summary.json"
        changed = json.loads(target.read_text())
        changed["source"]["sha256"] = first["source"]["sha256"]
        write_json(target, changed)
        with self.assertRaisesRegex(ValueError, "leakage"):
            read_manifest(self.manifest)

    def test_corrupt_sequence_and_unreviewed_labels_are_rejected(self):
        sequence = self.root / "data/fixture_00/sequence.jsonl"
        with sequence.open("a") as stream:
            stream.write("{}\n")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            load_features(sequence.parent)
        manifest = json.loads(self.manifest.read_text())
        manifest["purpose"] = "attitude_training"
        write_json(self.manifest, manifest)
        with self.assertRaisesRegex(ValueError, "reviewed"):
            read_manifest(self.manifest)

    def test_no_valid_features_is_rejected(self):
        directory = self.root / "data/fixture_00"
        sequence = directory / "sequence.jsonl"
        records = [json.loads(line) for line in sequence.read_text().splitlines()]
        for record in records:
            record["valid"] = {p: False for p in record["valid"]}
            record["smoothed_xy"] = {p: None for p in record["valid"]}
        sequence.write_text("".join(json.dumps(row) + "\n" for row in records))
        summary = json.loads((directory / "summary.json").read_text())
        summary["sequence_sha256"] = sha256(sequence)
        write_json(directory / "summary.json", summary)
        with self.assertRaisesRegex(ValueError, "No usable"):
            load_features(directory)

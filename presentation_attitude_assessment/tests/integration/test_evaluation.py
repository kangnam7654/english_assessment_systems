import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import torch

from presentation_attitude.artifacts import read_json, write_json
from presentation_attitude.pipelines.evaluation import evaluate
from presentation_attitude.pipelines.training import train
from presentation_attitude.pipelines.training_smoke import create_smoke_manifest


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.training = create_smoke_manifest(self.root / "training-data")
        self.test = create_smoke_manifest(
            self.root / "test-data", seed=43, test_only=True
        )
        train(self.training, self.root / "training", epochs=1, hidden_size=8)
        self.checkpoint = self.root / "training/best.pt"
        self.output = self.root / "evaluation"

    def evaluate(self, **kwargs):
        return evaluate(
            self.checkpoint,
            self.test,
            self.training,
            self.output,
            device="cpu",
            **kwargs,
        )

    def test_cli_produces_predictions_mistakes_and_metrics_without_changing_weights(
        self,
    ):
        original = self.checkpoint.read_bytes()
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "presentation_attitude.cli.evaluate",
                "--checkpoint",
                str(self.checkpoint),
                "--manifest",
                str(self.test),
                "--training-manifest",
                str(self.training),
                "--output",
                str(self.output),
                "--device",
                "cpu",
                "--threshold",
                "1",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = read_json(self.output / "summary.json")
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["purpose"], "pipeline_smoke")
        self.assertEqual(report["provenance_basis"], "checkpoint_snapshot")
        predictions = [
            json.loads(line)
            for line in (self.output / "predictions.jsonl").read_text().splitlines()
        ]
        mistakes = [
            json.loads(line)
            for line in (self.output / "misclassifications.jsonl")
            .read_text()
            .splitlines()
        ]
        self.assertEqual(len(predictions), 4)
        positive_scores = [
            p["positive_class_probability"] for p in predictions if p["true_label"] == 1
        ]
        negative_scores = [
            p["positive_class_probability"] for p in predictions if p["true_label"] == 0
        ]
        expected_auc = sum(
            (positive > negative) + 0.5 * (positive == negative)
            for positive in positive_scores
            for negative in negative_scores
        ) / (len(positive_scores) * len(negative_scores))
        self.assertEqual(report["metrics"]["roc_auc"], expected_auc)
        self.assertEqual(mistakes, [p for p in predictions if not p["correct"]])
        self.assertEqual(len(mistakes), 2)
        self.assertEqual(
            report["metrics"]["confusion_matrix"]["values"], [[2, 0], [2, 0]]
        )
        self.assertEqual(self.checkpoint.read_bytes(), original)
        with self.assertRaises(FileExistsError):
            self.evaluate()

    def test_train_or_validation_manifest_cannot_be_used_as_test(self):
        with self.assertRaisesRegex(ValueError, "splits"):
            evaluate(
                self.checkpoint, self.training, self.training, self.output, device="cpu"
            )

    def test_identity_and_content_leakage_rejected(self):
        original = read_json(self.test)
        train_sample = read_json(self.training)["samples"][0]
        train_summary = read_json(
            self.training.parent / train_sample["sequence_dir"] / "summary.json"
        )
        first = original["samples"][0]
        summary_path = self.test.parent / first["sequence_dir"] / "summary.json"
        original_summary = read_json(summary_path)
        for key in (
            "id",
            "speaker_id",
            "source_video_id",
            "source_sha256",
            "sequence_sha256",
        ):
            manifest, summary = (
                json.loads(json.dumps(original)),
                json.loads(json.dumps(original_summary)),
            )
            if key == "source_sha256":
                summary["source"]["sha256"] = train_summary["source"]["sha256"]
            elif key == "sequence_sha256":
                summary[key] = train_summary[key]
            else:
                manifest["samples"][0][key] = train_sample[key]
            write_json(self.test, manifest)
            write_json(summary_path, summary)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "leakage"):
                self.evaluate()
            self.assertFalse(self.output.exists())

    def test_changed_training_provenance_is_rejected(self):
        path = self.training.parent / "fixture_00/summary.json"
        summary = read_json(path)
        summary["source"]["sha256"] = "changed"
        write_json(path, summary)
        with self.assertRaisesRegex(ValueError, "provenance changed"):
            self.evaluate()

    def test_checkpoint_manifest_and_label_mapping_must_match(self):
        state = torch.load(self.checkpoint, weights_only=True)
        state["manifest_sha256"] = "other"
        torch.save(state, self.checkpoint)
        with self.assertRaisesRegex(ValueError, "Training manifest"):
            self.evaluate()
        from presentation_attitude.artifacts import sha256

        state["manifest_sha256"] = sha256(self.training)
        state["label_mapping"] = {"0": "appropriate", "1": "inappropriate"}
        torch.save(state, self.checkpoint)
        with self.assertRaisesRegex(ValueError, "label mapping"):
            self.evaluate()

    def test_corrupt_sequence_marks_failed_without_partial_metrics(self):
        sample = read_json(self.test)["samples"][1]
        with (self.test.parent / sample["sequence_dir"] / "sequence.jsonl").open(
            "a"
        ) as stream:
            stream.write("{}\n")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.evaluate()
        report = read_json(self.output / "summary.json")
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["processed_samples"], 1)
        self.assertIsNone(report["metrics"])
        self.assertIsNone(report["predictions_file"])
        self.assertFalse((self.output / "predictions.jsonl").exists())

    def test_legacy_checkpoint_and_single_class_test_set(self):
        state = torch.load(self.checkpoint, weights_only=True)
        del state["training_sample_provenance"]
        torch.save(state, self.checkpoint)
        manifest = read_json(self.test)
        manifest["samples"] = [s for s in manifest["samples"] if s["label"] == 0]
        write_json(self.test, manifest)
        result = self.evaluate()
        self.assertEqual(result["metrics"]["samples"], 2)
        self.assertEqual(
            result["provenance_basis"], "supplied_training_manifest_legacy_checkpoint"
        )
        self.assertIsNone(result["metrics"]["recall"])
        self.assertIsNone(result["metrics"]["roc_auc"])

    @unittest.skipUnless(torch.backends.mps.is_available(), "MPS unavailable")
    def test_mps_inference_matches_cpu(self):
        cpu = self.evaluate()
        mps = evaluate(
            self.checkpoint, self.test, self.training, self.root / "mps", device="mps"
        )
        self.assertEqual(mps["device"], "mps")
        self.assertEqual(cpu["metrics"]["roc_auc"], mps["metrics"]["roc_auc"])
        self.assertEqual(
            cpu["metrics"]["confusion_matrix"], mps["metrics"]["confusion_matrix"]
        )
        left = (self.output / "predictions.jsonl").read_text().splitlines()
        right = (self.root / "mps/predictions.jsonl").read_text().splitlines()
        for a, b in zip(left, right):
            self.assertAlmostEqual(
                json.loads(a)["positive_class_probability"],
                json.loads(b)["positive_class_probability"],
                places=5,
            )

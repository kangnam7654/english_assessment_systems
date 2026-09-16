"""Regression checks for examples."""

import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from child_speech.reporting import build_examples as examples


class ExampleTests(unittest.TestCase):
    """Exercise example tests behavior with controlled fixtures."""
    def test_word_errors_include_insertions_deletions_substitutions(self):
        """Verify word errors include insertions deletions substitutions."""
        self.assertEqual(examples.errors("a b c".split(), "a x c d".split()), 2)
        self.assertEqual(examples.errors("a b c".split(), ["a"]), 2)

    def test_spelling_is_not_silently_normalized(self):
        """Verify spelling is not silently normalized."""
        self.assertEqual(examples.normalize("It’s FINE!"), "it's fine")
        self.assertNotEqual(
            examples.normalize("favourite"), examples.normalize("favorite")
        )

    def test_mismatched_reference_rejected(self):
        """Verify mismatched reference rejected."""
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder) / "a.jsonl", Path(folder) / "b.jsonl"
            row = dict(
                audio_filename="sample",
                audio_sha256="hash",
                audio_member="sample.wav",
                text="a",
                hypothesis="a",
            )
            a.write_text(json.dumps(row) + "\n")
            b.write_text(json.dumps({**row, "text": "b"}) + "\n")
            with self.assertRaises(ValueError):
                examples.paired(a, b)

    def test_public_metrics_are_consistent(self):
        """Verify public metrics are consistent."""
        report = json.loads((ROOT / "results/test.json").read_text())
        self.assertEqual(report["before"]["count"], 4567)
        self.assertEqual(report["after"]["count"], 4567)
        self.assertAlmostEqual(
            report["relative_wer_reduction_percent"],
            100 * (1 - report["after"]["wer"] / report["before"]["wer"]),
        )
        samples = json.loads((ROOT / "results/examples.json").read_text())["examples"]
        self.assertEqual(
            [r["outcome"] for r in samples], ["improved"] * 3 + ["regressed"]
        )
        self.assertTrue(
            all("text" not in r and "audio_member" not in r for r in samples)
        )

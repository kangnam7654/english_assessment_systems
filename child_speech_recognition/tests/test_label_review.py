"""Check that private label curation cannot silently alter references."""

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from child_speech.data import label_review


class LabelReviewTests(unittest.TestCase):
    """Exercise candidate review and approved-decision boundaries."""

    def setUp(self) -> None:
        """Create a tiny AI Hub-shaped label archive in a temporary directory."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / "labels.zip"
        labels = [
            ("a.wav", "I wil consult the doctor."),
            ("b.wav", "no it''s not good idea."),
            ("c.wav", "NNN sees a rose"),
            ("d.wav", "I see a tree."),
        ]
        with zipfile.ZipFile(self.archive, "w") as output:
            for filename, transcript in labels:
                record = {
                    "File": {"FileName": filename},
                    "Transcription": {"LabelText": transcript},
                }
                output.writestr(f"labels/{filename}.json", json.dumps(record))
        self.original_hash = label_review.file_hash(self.archive)

    def decisions(self, corrections: list[dict[str, str]]) -> Path:
        """Write private approvals bound to the test archive hash.

        Args:
            corrections: Approved or deliberately invalid correction records.

        Returns:
            Path to a JSON decisions file.
        """
        path = self.root / "decisions.json"
        path.write_text(
            json.dumps(
                {"source_sha256": self.original_hash, "corrections": corrections}
            ),
            encoding="utf-8",
        )
        return path

    def test_queue_is_advisory_and_only_approved_changes_are_applied(self) -> None:
        """Keep ASR disagreements as candidates and exclude NNN without guessing text."""
        suggestions = self.root / "suggestions.jsonl"
        suggestions.write_text(
            json.dumps(
                {"audio_filename": "a.wav", "hypothesis": "I will consult the doctor."}
            )
            + "\n"
            + json.dumps({"audio": "d.wav", "hypothesis": "I saw a tree."})
            + "\n",
            encoding="utf-8",
        )
        queue_dir = self.root / "queue"
        label_review.run(
            [
                "queue",
                "--labels",
                str(self.archive),
                "--suggestions",
                str(suggestions),
                "--output-dir",
                str(queue_dir),
            ]
        )
        queue = [
            json.loads(line)
            for line in (queue_dir / "review-queue.jsonl").read_text().splitlines()
        ]
        self.assertEqual(
            {row["audio_filename"] for row in queue},
            {"a.wav", "b.wav", "c.wav", "d.wav"},
        )
        self.assertEqual(queue[2]["reasons"], ["explicit_nnn_placeholder"])

        decisions = self.decisions(
            [
                {
                    "audio_filename": "a.wav",
                    "before": "I wil consult the doctor.",
                    "after": "I will consult the doctor.",
                    "reason": "explicit spelling typo",
                    "status": "approved",
                },
                {
                    "audio_filename": "b.wav",
                    "before": "no it''s not good idea.",
                    "after": "no it's not good idea.",
                    "reason": "duplicate apostrophe",
                    "status": "approved",
                },
            ]
        )
        curated_dir = self.root / "curated"
        label_review.run(
            [
                "apply",
                "--labels",
                str(self.archive),
                "--decisions",
                str(decisions),
                "--output-dir",
                str(curated_dir),
            ]
        )
        eligible = [
            json.loads(line)
            for line in (curated_dir / "eligible.jsonl").read_text().splitlines()
        ]
        excluded = [
            json.loads(line)
            for line in (curated_dir / "excluded.jsonl").read_text().splitlines()
        ]
        self.assertEqual(len(eligible), 3)
        self.assertEqual(len(excluded), 1)
        self.assertEqual(eligible[0]["text_original"], "I wil consult the doctor.")
        self.assertEqual(eligible[0]["text"], "I will consult the doctor.")
        self.assertEqual(eligible[2]["text"], "I see a tree.")
        self.assertEqual(excluded[0]["exclusion_reason"], "explicit_nnn_placeholder")
        self.assertEqual(label_review.file_hash(self.archive), self.original_hash)

    def test_stale_or_unapproved_decisions_fail_before_writing(self) -> None:
        """Reject decisions that do not match the archive or lack approval."""
        correction = {
            "audio_filename": "a.wav",
            "before": "I wil consult the doctor.",
            "after": "I will consult the doctor.",
            "reason": "spelling typo",
            "status": "pending",
        }
        decisions = self.decisions([correction])
        output = self.root / "curated"
        args = [
            "apply",
            "--labels",
            str(self.archive),
            "--decisions",
            str(decisions),
            "--output-dir",
            str(output),
        ]
        with self.assertRaisesRegex(ValueError, "unapproved"):
            label_review.run(args)
        self.assertFalse(output.exists())

        correction["status"] = "approved"
        self.decisions([correction])
        document = json.loads(decisions.read_text())
        document["source_sha256"] = "0" * 64
        decisions.write_text(json.dumps(document))
        with self.assertRaisesRegex(ValueError, "does not match"):
            label_review.run(args)
        self.assertFalse(output.exists())

        correction["before"] = "A different source transcript."
        self.decisions([correction])
        with self.assertRaisesRegex(ValueError, "Invalid or unapproved"):
            label_review.run(args)
        self.assertFalse(output.exists())

        correction.update(
            audio_filename="c.wav", before="NNN sees a rose", after="Amy sees a rose"
        )
        self.decisions([correction])
        with self.assertRaisesRegex(ValueError, "Invalid or unapproved"):
            label_review.run(args)
        self.assertFalse(output.exists())

    def test_existing_output_directory_is_preserved(self) -> None:
        """Never overwrite an earlier private review artifact."""
        output = self.root / "queue"
        output.mkdir()
        marker = output / "keep.txt"
        marker.write_text("existing")
        with self.assertRaises(FileExistsError):
            label_review.run(
                ["queue", "--labels", str(self.archive), "--output-dir", str(output)]
            )
        self.assertEqual(marker.read_text(), "existing")

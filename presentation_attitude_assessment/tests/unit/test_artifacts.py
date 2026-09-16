"""Regression checks for artifacts."""

import json
import tempfile
import unittest
from pathlib import Path

from presentation_attitude.artifacts import (
    iter_jsonl,
    read_json,
    write_json,
    write_json_atomic,
    write_jsonl_row,
)


class ArtifactTests(unittest.TestCase):
    """Exercise artifact tests behavior with controlled fixtures."""
    def test_failed_status_serialization_preserves_previous_file(self):
        """Verify failed status serialization preserves previous file."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summary.json"
            write_json_atomic(path, {"status": "running"})
            with self.assertRaises(ValueError):
                write_json_atomic(path, {"loss": float("nan")})
            self.assertEqual(read_json(path), {"status": "running"})
            self.assertFalse(path.with_name("summary.json.tmp").exists())
            write_json_atomic(path, {"status": "complete"})
            self.assertEqual(read_json(path), {"status": "complete"})

    def test_exclusive_json_does_not_overwrite(self):
        """Verify exclusive json does not overwrite."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summary.json"
            write_json(path, {"keep": True}, exclusive=True)
            with self.assertRaises(FileExistsError):
                write_json(path, {"keep": False}, exclusive=True)
            self.assertEqual(read_json(path), {"keep": True})

    def test_jsonl_preserves_existing_serialization_and_streams_records(self):
        """Verify jsonl preserves existing serialization and streams records."""
        records = [{"label": "얼굴", "xy": None}, {"xy": [0.1, 0.2]}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sequence.jsonl"
            with path.open("w", encoding="utf-8") as stream:
                for record in records:
                    write_jsonl_row(stream, record)
            expected = "".join(
                json.dumps(record, separators=(",", ":"), allow_nan=False) + "\n"
                for record in records
            )
            self.assertEqual(path.read_text(), expected)
            self.assertEqual(list(iter_jsonl(path)), records)

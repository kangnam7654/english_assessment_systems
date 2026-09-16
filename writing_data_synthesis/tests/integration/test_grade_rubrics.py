"""Grade files are complete runtime inputs, with no common-template fallback."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from writing_synthesis.cli.materialize_project_rubrics import grade_documents
from writing_synthesis.criteria.catalog import ROOT
from writing_synthesis.criteria.resolver import ResolvedCriteria
from writing_synthesis.prompts.project import build_project_prompt


class GradeRubricTests(unittest.TestCase):
    """Exercise grade rubric tests behavior with controlled fixtures."""
    def test_every_materialized_grade_matches_the_existing_criteria(self):
        """Verify every materialized grade matches the existing criteria."""
        documents = grade_documents()
        self.assertEqual(len(documents), 13)
        self.assertEqual(sum(len(d["rubrics"]) for d in documents.values()), 39)
        for path, expected in documents.items():
            self.assertEqual(json.loads(path.read_bytes()), expected)
            for genre, selected in expected["rubrics"].items():
                resolved = ResolvedCriteria(
                    expected["grade"], genre, "project-writing-v1"
                )
                self.assertEqual(resolved.rubric, selected["rubric"])
                self.assertEqual(resolved.standards, selected["standards"])
                reference = resolved.reference("assessor")
                self.assertEqual(
                    reference.grade_file_sha256,
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
                self.assertEqual(
                    reference.rubric_sha256,
                    hashlib.sha256(resolved.rubric_bytes).hexdigest(),
                )
                self.assertNotIn("grade_genre_overrides", resolved.rubric)
                self.assertNotIn("by_genre", resolved.standards)

    def test_runtime_reads_grade_file_without_template_or_standards_files(self):
        """Verify runtime reads grade file without template or standards files."""
        original = json.loads((ROOT / "grades/grade-6.json").read_bytes())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "grades/grade-6.json"
            path.parent.mkdir(parents=True)
            original["rubrics"]["argumentative"]["rubric"]["dimensions"][
                "task_content"
            ]["3"] = "Grade file test marker."
            path.write_text(json.dumps(original))
            with patch("writing_synthesis.criteria.resolver.ROOT", root):
                resolved = ResolvedCriteria(
                    "us_6", "argumentative", "project-writing-v1"
                )
                prompt = build_project_prompt(
                    resolved, "assessor", source_use_applicable=True
                )
                self.assertIn("Grade file test marker.", prompt)
                # A missing grade cannot silently revert to the authoring template.
                with self.assertRaises(FileNotFoundError):
                    ResolvedCriteria("us_7", "argumentative", "project-writing-v1")
                original["grade"] = "us_7"
                path.write_text(json.dumps(original))
                with self.assertRaisesRegex(ValueError, "identity mismatch"):
                    ResolvedCriteria("us_6", "argumentative", "project-writing-v1")

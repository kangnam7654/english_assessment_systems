"""Checks for the public ASR results overview graphic."""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from child_speech.reporting import results_overview as overview

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "docs/assets/asr-results-overview.svg"
SVG = "{http://www.w3.org/2000/svg}"
DELETE = object()


def load_public():
    """Load fresh copies of the committed public result files.

    Returns:
        Tuple of parsed ``test.json`` and ``examples.json``.
    """
    return (
        json.loads((ROOT / "results/test.json").read_text(encoding="utf-8")),
        json.loads((ROOT / "results/examples.json").read_text(encoding="utf-8")),
    )


def changed(target, path, value):
    """Return public data with one nested value replaced or deleted.

    Args:
        target: ``"test"`` or ``"examples"``.
        path: Keys and list indices leading to the value.
        value: Replacement value, or ``DELETE`` to remove the key.

    Returns:
        Tuple of modified ``test`` and ``examples`` data.
    """
    test, examples = load_public()
    node = test if target == "test" else examples
    for key in path[:-1]:
        node = node[key]
    if value is DELETE:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    return test, examples


def visible_text(svg):
    """Parse SVG as XML and return the content of its text elements.

    Args:
        svg: SVG document text.

    Returns:
        Text element contents joined by newlines.
    """
    root = ET.fromstring(svg)
    return "\n".join("".join(node.itertext()) for node in root.iter(f"{SVG}text"))


def run_cli(*args):
    """Run the command-line entry point with captured output.

    Args:
        *args: Command-line arguments.

    Returns:
        Exit status.
    """
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return overview.main(list(args))


class ResultsOverviewTests(unittest.TestCase):
    """Exercise rendering, validation and drift detection for the overview SVG."""

    def test_rendering_is_deterministic_and_matches_committed_asset(self):
        """Verify repeated renders are identical and equal the committed SVG."""
        svg = overview.build_svg(ROOT / "results/test.json", ROOT / "results/examples.json")
        self.assertEqual(svg, overview.render_svg(overview.summarize(*load_public())))
        self.assertEqual(svg, overview.render_svg(overview.summarize(*load_public())))
        self.assertEqual(ASSET.read_bytes(), svg.encode("utf-8"))

    def test_source_is_fixed_to_committed_public_results(self):
        """Ignore training-project overrides when checking the public graphic."""
        with tempfile.TemporaryDirectory() as folder:
            env = {**os.environ, "ASR_PROJECT_DIR": folder, "PYTHONPATH": str(ROOT / "src")}
            result = subprocess.run(
                [sys.executable, "-B", "-m", "child_speech.reporting.results_overview", "--check"],
                cwd=ROOT.parent,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("is up to date", result.stdout)

    def test_svg_is_accessible_standalone_markup(self):
        """Verify the SVG has a title, description and no scripts or external links."""
        svg = ASSET.read_text(encoding="utf-8")
        root = ET.fromstring(svg)
        self.assertEqual(root.tag, f"{SVG}svg")
        self.assertEqual(root.get("role"), "img")
        self.assertTrue(root.get("viewBox"))
        self.assertTrue(root.find(f"{SVG}title").text)
        self.assertIn("14.45%", root.find(f"{SVG}desc").text)
        external = svg.replace('xmlns="http://www.w3.org/2000/svg"', "")
        for token in ("http", "href", "<script", "<image", "url(", "@import"):
            self.assertNotIn(token, external)

    def test_values_come_from_public_json(self):
        """Verify shown numbers and sentences follow the stored public data."""
        text = visible_text(ASSET.read_text(encoding="utf-8"))
        for expected in (
            "NEW AI HUB EXPERIMENT",
            "Not the portfolio's historical company WER.",
            "14.45%",
            "8.50%",
            "Same 4,567 Test recordings for both",
            "Improved: word errors 1 → 0",
            "Grandpa's house is in Soul.",
            "Grandpa's house is in Seoul",
            "Regressed: word errors 0 → 1",
            "And Grandpa read me a book.",
            "And grandpa reads me a book",
            "Showing 2 of 4 published examples.",
            "Illustrative, not a random sample;",
        ):
            self.assertIn(expected, text)

        test, examples = load_public()
        test["before"]["wer"], test["after"]["wer"] = 0.2, 0.125
        for record in (test["before"], test["after"]):
            record["count"] = 1234
        test["paired_records_verified"] = 1234
        examples["examples"][2]["after"] = "Changed stored output"
        examples["examples"][3]["after_word_errors"] = 2
        text = visible_text(overview.render_svg(overview.summarize(test, examples)))
        for expected in ("20.00%", "12.50%", "Same 1,234 Test recordings", "Changed stored output", "0 → 2"):
            self.assertIn(expected, text)
        for stale in ("14.45%", "8.50%", "4,567", "Seoul"):
            self.assertNotIn(stale, text)

    def test_injected_text_is_escaped(self):
        """Verify markup in stored text cannot create SVG elements or attributes."""
        test, examples = load_public()
        payload = "</text><script>alert(1)</script>&amp;"
        examples["examples"][2]["before"] = payload
        examples["selection"] = '"><svg onload=alert(1)> <!-- x -->'
        svg = overview.render_svg(overview.summarize(test, examples))
        root = ET.fromstring(svg)
        self.assertEqual(len(list(root.iter(f"{SVG}svg"))), 1)
        self.assertEqual(list(root.iter(f"{SVG}script")), [])
        self.assertNotIn("<script", svg)
        self.assertNotIn("<svg onload", svg)
        self.assertIn("&lt;/text&gt;&lt;script&gt;", svg)
        self.assertIn("&amp;amp;", svg)
        self.assertIn(payload, visible_text(svg))

    def test_malformed_or_inconsistent_data_is_rejected(self):
        """Verify missing, non-finite, mistyped or mismatched data raises an error."""
        cases = {
            "missing after": ("test", ["after"], DELETE),
            "missing wer": ("test", ["before", "wer"], DELETE),
            "nan wer": ("test", ["before", "wer"], float("nan")),
            "infinite wer": ("test", ["after", "wer"], float("inf")),
            "string wer": ("test", ["after", "wer"], "0.08"),
            "rate above one": ("test", ["after", "wer"], 1.5),
            "boolean count": ("test", ["before", "count"], True),
            "count mismatch": ("test", ["after", "count"], 4566),
            "paired mismatch": ("test", ["paired_records_verified"], 4000),
            "outcome mismatch": ("examples", ["examples", 2, "outcome"], "regressed"),
            "errors contradict outcome": ("examples", ["examples", 3, "after_word_errors"], 0),
            "negative errors": ("examples", ["examples", 2, "after_word_errors"], -1),
            "missing featured example": ("examples", ["examples", 3], DELETE),
            "duplicate example": ("examples", ["examples", 1, "example"], 3),
            "empty output": ("examples", ["examples", 2, "before"], " "),
            "control character": ("examples", ["examples", 3, "after"], "book\x00"),
            "examples not list": ("examples", ["examples"], {}),
            "missing selection": ("examples", ["selection"], DELETE),
        }
        for name, (target, path, value) in cases.items():
            with self.subTest(name):
                with self.assertRaises(overview.ResultsDataError):
                    overview.summarize(*changed(target, path, value))

    def test_non_finite_or_malformed_json_files_are_rejected(self):
        """Verify the loader rejects NaN, Infinity, overflow and invalid JSON."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.json"
            for text in ('{"wer": NaN}', '{"wer": -Infinity}', "{"):
                with self.subTest(text):
                    path.write_text(text, encoding="utf-8")
                    with self.assertRaises(overview.ResultsDataError):
                        overview.load_json(path)
            test, examples = load_public()
            path.write_text(
                json.dumps(test).replace(str(test["after"]["wer"]), "1e999"), encoding="utf-8"
            )
            with self.assertRaises(overview.ResultsDataError):
                overview.summarize(overview.load_json(path), examples)

    def test_check_detects_drift(self):
        """Verify --check passes for a fresh render and fails on drift or absence."""
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "nested" / "overview.svg"
            self.assertEqual(run_cli("--check", "--output", str(output)), 1)
            self.assertEqual(run_cli("--output", str(output)), 0)
            self.assertEqual(run_cli("--check", "--output", str(output)), 0)
            output.write_text(
                output.read_text(encoding="utf-8").replace("8.50%", "7.50%"), encoding="utf-8"
            )
            self.assertEqual(run_cli("--check", "--output", str(output)), 1)

    def test_svg_has_no_audio_labels_or_paths(self):
        """Verify reference text, audio fields and file paths never reach the SVG."""
        test, examples = load_public()
        for row in examples["examples"]:
            row.update(
                text="SECRET REFERENCE LABEL",
                audio_filename="clip-secret-id",
                audio_member="private/clip.wav",
                audio_sha256="deadbeefcafe",
            )
        test["source"] = "/Users/someone/.local-data/test-0.jsonl"
        svg = overview.render_svg(overview.summarize(test, examples))
        for token in (
            "SECRET REFERENCE LABEL",
            "clip-secret-id",
            "deadbeefcafe",
            ".wav",
            ".zip",
            ".json",
            ".local-data",
            "/Users",
            "results/",
            "base64",
        ):
            self.assertNotIn(token, svg)
        self.assertEqual(svg, ASSET.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

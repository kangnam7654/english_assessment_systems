"""Render the public ASR results overview SVG from committed result JSON.

The graphic is built only from ``results/test.json`` and ``results/examples.json``.
It shows the stored before/after Test WER of the new AI Hub experiment and two
already published model outputs with their stored word-error counts. No audio,
reference labels or file paths are read into or written to the image, and no new
quality metric is computed.

Example:
    Regenerate, or verify, the committed graphic from the repository root::

        PYTHONPATH=child_speech_recognition/src python3 -m child_speech.reporting.results_overview
        PYTHONPATH=child_speech_recognition/src python3 -m child_speech.reporting.results_overview --check
"""

import argparse
import html
import json
import math
import re
import sys
from pathlib import Path

# Locate the committed ASR project beside this module. Do not honor the training
# pipeline's ASR_PROJECT_DIR override: this public graphic must not read another
# directory's results when someone runs the render/check command.
PROJECT_DIR = Path(__file__).resolve().parents[3]
TEST_PATH = PROJECT_DIR / "results" / "test.json"
EXAMPLES_PATH = PROJECT_DIR / "results" / "examples.json"
OUTPUT_PATH = PROJECT_DIR / "docs" / "assets" / "asr-results-overview.svg"

# Published examples shown in the graphic: (example number, expected outcome).
FEATURED_EXAMPLES = ((3, "improved"), (4, "regressed"))

WIDTH = 600
MARGIN = 32
RIGHT = WIDTH - MARGIN
SENTENCE_X = 136
SENTENCE_CHARS = 32
SELECTION_CHARS = 50
TITLE = "Child English ASR results overview"

STYLE = """  <style>
    text { font-family: system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif; fill: #111827; }
    .tag { font-size: 20px; font-weight: 700; fill: #1d4ed8; letter-spacing: 1px; }
    .h1 { font-size: 36px; font-weight: 700; }
    .note { font-size: 22px; fill: #374151; }
    .label { font-size: 24px; font-weight: 700; }
    .big { font-size: 64px; font-weight: 700; }
    .before { fill: #6b7280; }
    .after { fill: #047857; }
    .arrow { font-size: 48px; fill: #6b7280; }
    .small { font-size: 20px; fill: #4b5563; }
    .sentence { font-size: 24px; }
    .improved { font-size: 22px; font-weight: 700; fill: #047857; }
    .regressed { font-size: 22px; font-weight: 700; fill: #b45309; }
    .rule { stroke: #d1d5db; stroke-width: 2; }
  </style>"""

# Characters that XML 1.0 cannot represent, even when escaped.
_INVALID_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ud800-\udfff￾￿]")


class ResultsDataError(ValueError):
    """Raised when public result JSON is missing, malformed or inconsistent."""


def _reject_constant(name):
    """Reject the non-standard JSON constants ``NaN`` and ``Infinity``.

    Args:
        name: Constant name reported by the JSON parser.

    Raises:
        ResultsDataError: Always, because the constant is not a finite number.
    """
    raise ResultsDataError(f"Non-finite JSON number: {name}")


def load_json(path):
    """Read a public result file, rejecting malformed or non-finite JSON.

    Args:
        path: JSON file to read.

    Returns:
        Parsed JSON value.

    Raises:
        ResultsDataError: The file is unreadable, malformed or contains NaN/Infinity.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ResultsDataError(f"Cannot read {path.name}") from error
    try:
        return json.loads(text, parse_constant=_reject_constant)
    except json.JSONDecodeError as error:
        raise ResultsDataError(f"Malformed JSON in {path.name}") from error


def escape_xml(text):
    """Escape text for an SVG text node or attribute value.

    Args:
        text: Text to escape.

    Returns:
        Text with ``&``, ``<``, ``>`` and both quote characters escaped.

    Raises:
        ResultsDataError: Text is not a string or contains XML-invalid characters.
    """
    if not isinstance(text, str) or _INVALID_XML.search(text):
        raise ResultsDataError("Text contains characters that cannot appear in XML")
    return html.escape(text, quote=True)


def _field(mapping, key, where):
    """Return a required key from a JSON object.

    Args:
        mapping: Parsed JSON value expected to be an object.
        key: Required key.
        where: Location used in error messages.

    Returns:
        Stored value for ``key``.

    Raises:
        ResultsDataError: The value is not an object or the key is missing.
    """
    if not isinstance(mapping, dict) or key not in mapping:
        raise ResultsDataError(f"Missing {where}.{key}")
    return mapping[key]


def _rate(value, where):
    """Validate a stored error rate.

    Args:
        value: Stored value.
        where: Location used in error messages.

    Returns:
        The rate as a float.

    Raises:
        ResultsDataError: The value is not a finite number between 0 and 1.
    """
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 1
    ):
        raise ResultsDataError(f"{where} must be a finite rate between 0 and 1")
    return float(value)


def _integer(value, where, minimum):
    """Validate a stored integer count.

    Args:
        value: Stored value.
        where: Location used in error messages.
        minimum: Smallest accepted value.

    Returns:
        The validated integer.

    Raises:
        ResultsDataError: The value is not an integer of at least ``minimum``.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ResultsDataError(f"{where} must be an integer >= {minimum}")
    return value


def _string(value, where):
    """Validate stored display text.

    Args:
        value: Stored value.
        where: Location used in error messages.

    Returns:
        The unchanged string.

    Raises:
        ResultsDataError: The value is empty, not a string or not XML-safe.
    """
    if not isinstance(value, str) or not value.strip() or _INVALID_XML.search(value):
        raise ResultsDataError(f"{where} must be non-empty XML-safe text")
    return value


def summarize(test, examples):
    """Collect and validate the stored values shown in the graphic.

    Args:
        test: Parsed ``results/test.json``.
        examples: Parsed ``results/examples.json``.

    Returns:
        Dictionary with stored before/after WER, Test count, selection text,
        published and shown example counts, and the featured examples.

    Raises:
        ResultsDataError: Data is missing, non-finite or internally inconsistent.
    """
    before = _field(test, "before", "test")
    after = _field(test, "after", "test")
    count = _integer(_field(before, "count", "test.before"), "test.before.count", 1)
    after_count = _integer(_field(after, "count", "test.after"), "test.after.count", 1)
    paired = _integer(
        _field(test, "paired_records_verified", "test"),
        "test.paired_records_verified",
        1,
    )
    if not count == after_count == paired:
        raise ResultsDataError("Before, after and paired Test counts differ")

    rows = _field(examples, "examples", "examples")
    if not isinstance(rows, list) or not rows:
        raise ResultsDataError("examples.examples must be a non-empty list")
    by_number = {}
    for row in rows:
        number = _integer(_field(row, "example", "examples[]"), "examples[].example", 1)
        if number in by_number:
            raise ResultsDataError(f"Duplicate example number {number}")
        by_number[number] = row

    featured = []
    for number, expected in FEATURED_EXAMPLES:
        if number not in by_number:
            raise ResultsDataError(f"Published example {number} is missing")
        row, where = by_number[number], f"examples[{number}]"
        before_errors = _integer(
            _field(row, "before_word_errors", where), f"{where}.before_word_errors", 0
        )
        after_errors = _integer(
            _field(row, "after_word_errors", where), f"{where}.after_word_errors", 0
        )
        if after_errors < before_errors:
            implied = "improved"
        elif after_errors > before_errors:
            implied = "regressed"
        else:
            implied = "unchanged"
        if _field(row, "outcome", where) != expected or implied != expected:
            raise ResultsDataError(f"{where} is not the expected {expected} example")
        featured.append(
            {
                "outcome": expected,
                "before": _string(_field(row, "before", where), f"{where}.before"),
                "after": _string(_field(row, "after", where), f"{where}.after"),
                "before_errors": before_errors,
                "after_errors": after_errors,
            }
        )

    return {
        "before_wer": _rate(_field(before, "wer", "test.before"), "test.before.wer"),
        "after_wer": _rate(_field(after, "wer", "test.after"), "test.after.wer"),
        "count": count,
        "selection": _string(
            _field(examples, "selection", "examples"), "examples.selection"
        ),
        "published": len(rows),
        "shown": len(featured),
        "examples": featured,
    }


def format_percent(rate):
    """Format a stored rate as a percentage with two decimals.

    Args:
        rate: Rate between 0 and 1.

    Returns:
        Text such as ``"14.45%"``.
    """
    return f"{rate * 100:.2f}%"


def wrap_words(text, limit):
    """Greedily wrap text into lines of at most ``limit`` characters.

    Args:
        text: Text to wrap; runs of whitespace collapse to single spaces.
        limit: Maximum characters per line. Longer single words keep their own line.

    Returns:
        List of lines.
    """
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if current and len(candidate) > limit:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _text_element(x, y, content, css_class, anchor=None):
    """Build one escaped SVG text element.

    Args:
        x: Horizontal position.
        y: Baseline position.
        content: Text content, escaped here.
        css_class: CSS class names.
        anchor: Optional ``text-anchor`` value.

    Returns:
        SVG markup for the element.
    """
    anchor_attr = f' text-anchor="{anchor}"' if anchor else ""
    return (
        f'  <text x="{x}" y="{y}" class="{escape_xml(css_class)}"{anchor_attr}>'
        f"{escape_xml(content)}</text>"
    )


def _rule(y):
    """Build a horizontal divider.

    Args:
        y: Vertical position.

    Returns:
        SVG markup for the divider.
    """
    return f'  <line x1="{MARGIN}" y1="{y}" x2="{RIGHT}" y2="{y}" class="rule"/>'


def render_svg(summary):
    """Render the overview graphic as standalone SVG text.

    Args:
        summary: Values returned by :func:`summarize`.

    Returns:
        Deterministic SVG document ending with a newline.
    """
    before = format_percent(summary["before_wer"])
    after = format_percent(summary["after_wer"])
    count = f"{summary['count']:,}"
    body = [
        _text_element(MARGIN, 56, "NEW AI HUB EXPERIMENT", "tag"),
        _text_element(MARGIN, 104, "Child English ASR results", "h1"),
        _text_element(MARGIN, 144, "Parakeet fine-tuned on AI Hub data.", "note"),
        _text_element(MARGIN, 174, "Not the portfolio's historical company WER.", "note"),
        _rule(200),
        _text_element(MARGIN, 244, "Test WER, lower is better", "label"),
        _text_element(MARGIN, 320, before, "big before"),
        _text_element(WIDTH // 2, 320, "→", "arrow", "middle"),
        _text_element(RIGHT, 320, after, "big after", "end"),
        _text_element(MARGIN, 356, "Before fine-tuning", "small"),
        _text_element(RIGHT, 356, "After fine-tuning", "small", "end"),
        _text_element(MARGIN, 400, f"Same {count} Test recordings for both", "note"),
        _text_element(MARGIN, 430, "Own data split, not an official benchmark.", "note"),
        _rule(456),
        _text_element(MARGIN, 500, "Published model outputs", "label"),
    ]
    y = 500
    for example in summary["examples"]:
        y += 46
        arrow = f"{example['before_errors']} → {example['after_errors']}"
        body.append(
            _text_element(
                MARGIN,
                y,
                f"{example['outcome'].capitalize()}: word errors {arrow}",
                example["outcome"],
            )
        )
        for stage in ("before", "after"):
            y += 36
            body.append(_text_element(MARGIN, y, stage.capitalize(), "small"))
            for index, line in enumerate(wrap_words(example[stage], SENTENCE_CHARS)):
                y += 32 if index else 0
                body.append(_text_element(SENTENCE_X, y, line, "sentence"))
    body.append(_rule(y + 30))
    y += 74
    for line in (
        f"Showing {summary['shown']} of {summary['published']} published examples.",
        "Illustrative, not a random sample;",
        "judge overall quality by Test WER.",
    ):
        body.append(_text_element(MARGIN, y, line, "note"))
        y += 30
    y += 10
    body.append(_text_element(MARGIN, y, "Stored selection rule:", "small"))
    for line in wrap_words(summary["selection"], SELECTION_CHARS):
        y += 28
        body.append(_text_element(MARGIN, y, line, "small"))
    height = y + 40

    stories = " ".join(
        f"{example['outcome'].capitalize()} example: “{example['before']}” became "
        f"“{example['after']}”, word errors "
        f"{example['before_errors']} → {example['after_errors']}."
        for example in summary["examples"]
    )
    description = (
        "New AI Hub experiment, not the portfolio's historical company WER. "
        f"Test WER {before} before and {after} after fine-tuning on the same "
        f"{count} Test recordings. {stories} Illustrative examples, not a random sample."
    )
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
        f'viewBox="0 0 {WIDTH} {height}" role="img" aria-labelledby="asr-title asr-desc">',
        f'  <title id="asr-title">{escape_xml(TITLE)}</title>',
        f'  <desc id="asr-desc">{escape_xml(description)}</desc>',
        STYLE,
        f'  <rect width="{WIDTH}" height="{height}" fill="#ffffff"/>',
        *body,
        "</svg>",
    ]
    return "\n".join(parts) + "\n"


def build_svg(test_path=TEST_PATH, examples_path=EXAMPLES_PATH):
    """Load public result JSON and render the overview graphic.

    Args:
        test_path: Stored Test metrics JSON.
        examples_path: Stored public examples JSON.

    Returns:
        SVG document text.

    Raises:
        ResultsDataError: Data is missing, malformed, non-finite or inconsistent.
    """
    return render_svg(summarize(load_json(test_path), load_json(examples_path)))


def main(argv=None):
    """Regenerate the committed SVG or check that it is up to date.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        0 on success, 1 if ``--check`` finds a missing or outdated SVG, and 2 if
        the public result data is invalid.
    """
    parser = argparse.ArgumentParser(
        description="Regenerate or check the ASR results overview SVG."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit with status 1 if the SVG differs from the committed results",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help="SVG path (default: docs/assets/asr-results-overview.svg)",
    )
    args = parser.parse_args(argv)
    try:
        expected = build_svg().encode("utf-8")
    except ResultsDataError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.check:
        try:
            current = args.output.read_bytes()
        except OSError:
            current = None
        if current != expected:
            print(f"{args.output} is missing or out of date; rerun without --check.", file=sys.stderr)
            return 1
        print(f"{args.output} is up to date.")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(expected)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

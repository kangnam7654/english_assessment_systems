"""Prepare a human review queue and apply approved AI Hub label decisions.

Model suggestions are evidence for review, never replacements for the reference.
Original label archives remain unchanged; all outputs belong in a private folder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any

NNN = re.compile(r"(?<![A-Za-z0-9_])N{3,}(?![A-Za-z0-9_])", re.IGNORECASE)


def file_hash(path: Path) -> str:
    """Calculate a SHA-256 digest without loading the entire archive into memory.

    Args:
        path: Input label archive.

    Returns:
        Lowercase hexadecimal SHA-256 digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_labels(path: Path) -> list[dict[str, Any]]:
    """Read the transcript and identity of every JSON label in an AI Hub ZIP.

    Args:
        path: AI Hub label ZIP containing JSON members.

    Returns:
        Rows ordered by archive member name.

    Raises:
        ValueError: A label is empty, malformed, or has a duplicate audio filename.
    """
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    with zipfile.ZipFile(path) as archive:
        for member in sorted(
            name for name in archive.namelist() if name.endswith(".json")
        ):
            try:
                record = json.loads(archive.read(member))
                filename = record["File"]["FileName"]
                transcript = record["Transcription"]["LabelText"]
            except (KeyError, TypeError) as error:
                raise ValueError(f"Malformed label in {member}") from error
            if not isinstance(filename, str) or not filename or filename in seen:
                raise ValueError(f"Missing or duplicate audio filename in {member}")
            if not isinstance(transcript, str) or not transcript.strip():
                raise ValueError(f"Missing transcript in {member}")
            seen.add(filename)
            rows.append(
                {
                    "audio_filename": filename,
                    "label_archive": path.name,
                    "label_member": member,
                    "text": transcript,
                }
            )
    if not rows:
        raise ValueError("No JSON labels found in archive")
    return rows


def normalize(text: str) -> str:
    """Normalize only comparison formatting, preserving lexical differences.

    Args:
        text: Reference or independent model transcript.

    Returns:
        Lowercase words with punctuation and extra whitespace removed.
    """
    return " ".join(
        re.sub(r"[^a-z0-9'\s]", " ", text.lower().replace("’", "'")).split()
    )


def read_suggestions(path: Path, filenames: set[str]) -> dict[str, str]:
    """Index independent ASR suggestions without treating them as ground truth.

    Args:
        path: JSONL with ``hypothesis`` and ``audio_filename`` or ``audio``.
        filenames: Known audio filenames from the source label archive.

    Returns:
        Suggested transcript by audio filename.

    Raises:
        ValueError: A suggestion is malformed, duplicated, or refers to unknown audio.
        TypeError: A suggestion has an unexpected JSON field type.
    """
    suggestions: dict[str, str] = {}
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            item = json.loads(line)
            if not isinstance(item, dict):
                raise TypeError(f"Invalid suggestion at line {line_number}")
            raw_name = item.get("audio_filename") or item.get("audio")
            transcript = item.get("hypothesis")
            if not isinstance(raw_name, str) or not isinstance(transcript, str):
                raise TypeError(f"Invalid suggestion at line {line_number}")
            filename = raw_name.replace("\\", "/").rsplit("/", 1)[-1]
            if filename not in filenames or filename in suggestions:
                raise ValueError(f"Unknown or duplicate suggestion: {filename}")
            suggestions[filename] = transcript
    return suggestions


def review_queue(
    rows: list[dict[str, Any]], suggestions: dict[str, str]
) -> list[dict[str, Any]]:
    """Flag explicit placeholders, malformed apostrophes, and ASR disagreements.

    Args:
        rows: Source label rows.
        suggestions: Independent model transcripts keyed by audio filename.

    Returns:
        Candidate rows with reasons; no reference text is changed.
    """
    queue: list[dict[str, Any]] = []
    for row in rows:
        text = row["text"]
        hypothesis = suggestions.get(row["audio_filename"])
        reasons = []
        if NNN.search(text):
            reasons.append("explicit_nnn_placeholder")
        if "''" in text:
            reasons.append("duplicate_apostrophe")
        if hypothesis is not None and normalize(text) != normalize(hypothesis):
            reasons.append("asr_disagreement")
        if reasons:
            queue.append({**row, "hypothesis": hypothesis, "reasons": reasons})
    return queue


def read_approved_corrections(
    path: Path, source_sha256: str, rows: list[dict[str, Any]]
) -> dict[str, dict[str, str]]:
    """Validate exact, human-approved corrections against the original archive.

    Args:
        path: Private decisions JSON with source hash and corrections.
        source_sha256: SHA-256 of the input label ZIP.
        rows: Unmodified source label rows.

    Returns:
        Approved correction by audio filename.

    Raises:
        ValueError: A decision is stale, unapproved, ambiguous, or changes an excluded row.
        TypeError: The decisions JSON has an unexpected structure.
    """
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise TypeError("Decision file must be a JSON object")
    if document.get("source_sha256") != source_sha256:
        raise ValueError("Decision file does not match the source label archive")
    items = document.get("corrections")
    if not isinstance(items, list):
        raise TypeError("Decision file must contain a corrections list")
    source = {row["audio_filename"]: row["text"] for row in rows}
    corrections: dict[str, dict[str, str]] = {}
    for item in items:
        if not isinstance(item, dict):
            raise TypeError("Every correction must be a JSON object")
        filename = item.get("audio_filename")
        before, after = item.get("before"), item.get("after")
        reason = item.get("reason")
        if (
            item.get("status") != "approved"
            or not isinstance(filename, str)
            or filename not in source
            or filename in corrections
            or not isinstance(before, str)
            or source[filename] != before
            or NNN.search(before)
            or not isinstance(after, str)
            or not after.strip()
            or before == after
            or not isinstance(reason, str)
            or not reason.strip()
        ):
            raise ValueError(f"Invalid or unapproved correction: {filename}")
        corrections[filename] = {"before": before, "after": after, "reason": reason}
    return corrections


def apply_corrections(
    rows: list[dict[str, Any]], corrections: dict[str, dict[str, str]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Exclude explicit NNN markers and apply only approved transcript changes.

    Args:
        rows: Unmodified source label rows.
        corrections: Validated, approved corrections keyed by audio filename.

    Returns:
        Eligible rows and separately recorded excluded rows.
    """
    eligible: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for row in rows:
        if NNN.search(row["text"]):
            excluded.append({**row, "exclusion_reason": "explicit_nnn_placeholder"})
            continue
        item = dict(row)
        correction = corrections.get(row["audio_filename"])
        if correction is not None:
            item.update(
                text_original=row["text"],
                text=correction["after"],
                correction_reason=correction["reason"],
            )
        eligible.append(item)
    return eligible, excluded


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write private manifest rows in stable JSONL order.

    Args:
        path: New output file inside an output directory.
        rows: JSON-serializable records.
    """
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def run(argv: list[str] | None = None) -> None:
    """Generate a review queue or apply approvals to an untouched label ZIP.

    Args:
        argv: Optional command-line arguments; defaults to ``sys.argv``.

    Raises:
        FileExistsError: The requested private output directory already exists.
        ValueError: Input labels, suggestions, or decisions fail validation.
        TypeError: A suggestion or decision has an unexpected JSON field type.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name in ("queue", "apply"):
        command = subcommands.add_parser(name)
        command.add_argument("--labels", type=Path, required=True)
        command.add_argument("--output-dir", type=Path, required=True)
        if name == "queue":
            command.add_argument("--suggestions", type=Path)
        else:
            command.add_argument("--decisions", type=Path, required=True)
    args = parser.parse_args(argv)
    source_sha256 = file_hash(args.labels)
    rows = read_labels(args.labels)
    summary: dict[str, Any] = {
        "source_sha256": source_sha256,
        "source_count": len(rows),
    }

    if args.command == "queue":
        suggestions = (
            read_suggestions(args.suggestions, {row["audio_filename"] for row in rows})
            if args.suggestions
            else {}
        )
        output = review_queue(rows, suggestions)
        summary.update(suggestions=len(suggestions), review_candidates=len(output))
        filename = "review-queue.jsonl"
    else:
        corrections = read_approved_corrections(args.decisions, source_sha256, rows)
        output, excluded = apply_corrections(rows, corrections)
        summary.update(
            eligible=len(output),
            excluded_nnn=len(excluded),
            approved_corrections=len(corrections),
        )
        filename = "eligible.jsonl"

    args.output_dir.mkdir(parents=True, exist_ok=False)
    write_jsonl(args.output_dir / filename, output)
    if args.command == "apply":
        write_jsonl(args.output_dir / "excluded.jsonl", excluded)
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))

"""JSON output and file provenance shared by diagnostic workflows."""

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TextIO


def sha256(path: str | Path) -> str:
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, value: Any, *, exclusive: bool = False) -> None:
    text = json.dumps(value, indent=2, allow_nan=False) + "\n"
    with Path(path).open("x" if exclusive else "w", encoding="utf-8") as stream:
        stream.write(text)


def write_json_atomic(path: str | Path, value: Any) -> None:
    """Replace a status file after serializing finite JSON to a sibling file.

    The parent directory must exist and one writer must own each target path.
    Rename prevents partial JSON visibility; this is not a cross-process lock
    or an fsync-based guarantee against power loss.
    """
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    try:
        write_json(temporary, value)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def iter_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def write_jsonl_row(stream: TextIO, record: dict[str, Any]) -> None:
    stream.write(json.dumps(record, separators=(",", ":"), allow_nan=False) + "\n")


def implementation_hashes() -> dict[str, str]:
    """Hash the installed Python implementation, including CLI orchestration."""
    root = Path(__file__).parent
    return {
        str(path.relative_to(root)): sha256(path) for path in sorted(root.rglob("*.py"))
    }


def iter_sequence(output: str | Path) -> Iterator[dict[str, Any]]:
    """Validate and stream a completed whole-video sequence.

    Checks status/name and the full file hash before yielding, then enforces
    contiguous frame indices. The final frame-count check requires exhausting
    the iterator; consumers stopping early have not completed validation.
    """
    output = Path(output)
    summary = read_json(output / "summary.json")
    if summary["status"] != "complete" or summary["sequence_file"] != "sequence.jsonl":
        raise ValueError("A completed whole-video sequence is required")
    sequence = output / "sequence.jsonl"
    if sha256(sequence) != summary["sequence_sha256"]:
        raise ValueError("Sequence hash mismatch")
    count = 0
    for record in iter_jsonl(sequence):
        if record["raw"]["frame_index"] != count:
            raise ValueError("Sequence frame indices are not contiguous")
        count += 1
        yield record
    if count != summary["sampled_frames"]:
        raise ValueError("Sequence frame count mismatch")

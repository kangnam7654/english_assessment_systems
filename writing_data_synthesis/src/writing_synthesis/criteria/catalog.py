"""Source catalog lookup shared by request validation, prompts and result validation.

This module has no schema or agent dependencies. Archived rubric files remain readable
when defaults change, so saved assessments can retain their original score contract.
"""

import json
import re
from pathlib import Path
from typing import Any

from writing_synthesis.paths import PROJECT_DIR

ROOT = PROJECT_DIR / "criteria"


def routes() -> dict[str, dict[str, Any]]:
    """Load the grade/genre routing catalog from project resources.

    Returns:
        Grade/genre keys mapped to their configured rubric and standards routes.
    """
    return json.loads((ROOT / "routes.json").read_text())


def load_rubric(rubric_id: str) -> dict[str, Any]:
    """Load a known rubric and verify that its embedded identity matches its filename.

    Args:
        rubric_id: Explicit rubric identifier, or None to use the route default.

    Returns:
        Verified rubric document.

    Raises:
        ValueError: Invalid rubric identifier; Unknown rubric identifier; Rubric file
            identity mismatch.
    """
    if not re.fullmatch(r"[A-Za-z0-9-]+", rubric_id):
        raise ValueError("Invalid rubric identifier.")
    evidence = ROOT.parent / "docs/rubric-evidence"
    folder = (
        evidence if rubric_id == "project-writing-v1" else evidence / "source-rubrics"
    )
    path = folder / f"{rubric_id}.json"
    if not path.is_file():
        raise ValueError("Unknown rubric identifier.")
    rubric = json.loads(path.read_text())
    if rubric["id"] != rubric_id:
        raise ValueError("Rubric file identity mismatch.")
    return rubric


def select_route(
    grade: str, genre: str, rubric_id: str | None = None
) -> dict[str, Any]:
    """Resolve the default or explicitly supported rubric for one grade and genre.

    Args:
        grade: Requested US grade identifier, from us_K through us_12.
        genre: Requested writing genre.
        rubric_id: Explicit rubric identifier, or None to use the route default.

    Returns:
        Selected route with the requested or default rubric path.

    Raises:
        ValueError: Unsupported grade/genre combination; Rubric is not supported for
            this grade/genre.
    """
    route = routes().get(f"{grade}:{genre}")
    if route is None:
        raise ValueError("Unsupported grade/genre combination.")
    selected = route["rubric"]
    if rubric_id is not None:
        matches = [
            p
            for p in [selected, *route.get("alternatives", []), route["project_rubric"]]
            if Path(p).stem == rubric_id
        ]
        if not matches:
            raise ValueError("Rubric is not supported for this grade/genre.")
        selected = matches[0]
    return {**route, "rubric": selected}


def requires_sources(rubric: dict[str, Any], genre: str) -> bool:
    """Source requirements belong to the selected contract and task genre.

    Args:
        rubric: Loaded rubric with score ranges and task requirements.
        genre: Requested writing genre.

    Returns:
        Whether the selected rubric/genre requires supplied source passages.
    """
    return rubric.get("source_requirements_by_genre", {}).get(
        genre, rubric["requires_sources"]
    )


def source_use_applies(genre: str, has_sources: bool) -> bool:
    """The application decides applicability; a model cannot turn a score off.

    Args:
        genre: Requested writing genre.
        has_sources: Whether the request supplies source passages.

    Returns:
        True for a non-narrative task with supplied source passages.
    """
    return has_sources and genre != "narrative"


def available_routes(family: str = "source") -> list[dict[str, Any]]:
    """Expose defaults and explicit alternatives without leaking local file paths.

    Args:
        family: Rubric family to expose: source or project.

    Returns:
        Supported catalog options with score ranges and source provenance.

    Raises:
        ValueError: Unknown rubric family.
    """
    if family not in {"source", "project"}:
        raise ValueError("Unknown rubric family.")
    result = []
    for key, route in routes().items():
        grade, genre = key.split(":")
        paths = (
            [route["project_rubric"]]
            if family == "project"
            else [route["rubric"], *route.get("alternatives", [])]
        )
        for path in paths:
            rubric = load_rubric(Path(path).stem)
            result.append(
                {
                    "grade": grade,
                    "genre": genre,
                    "rubric_id": rubric["id"],
                    "rubric_version": rubric["adaptation_version"],
                    "provider": rubric["provider"],
                    "is_default": path == route["rubric"],
                    "requires_sources": requires_sources(rubric, genre),
                    "family": family,
                    "optional_score_ranges": {
                        k: v["range"]
                        for k, v in rubric.get("optional_dimensions", {}).items()
                        if genre != "narrative"
                    },
                    "source_urls": [s["source_url"] for s in rubric.get("sources", [])],
                    "score_ranges": rubric["score_ranges"],
                    "not_scorable_reasons": rubric["not_scorable"],
                    "scope_notes": rubric["scope_notes"],
                    "source_url": rubric["source_url"],
                    "notice": rubric["notice"],
                }
            )
    return result

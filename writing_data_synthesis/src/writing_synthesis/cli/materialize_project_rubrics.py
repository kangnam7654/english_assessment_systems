"""Build self-contained grade files offline; inference reads these files directly."""

import argparse
import copy
import json
from pathlib import Path

from writing_synthesis.criteria.catalog import ROOT, load_rubric, routes


def grade_documents() -> dict[Path, dict]:
    """Keep the established descriptors unchanged when organizing them by grade.

    Returns:
        Mapping from finalized grade JSON paths to their generated document contents.
    """
    template = load_rubric("project-writing-v1")
    documents = {}
    for key, route in routes().items():
        grade, genre = key.split(":")
        number = 0 if grade == "us_K" else int(grade[3:])
        band = (
            "K-2"
            if number <= 2
            else "3-5"
            if number <= 5
            else "6-8"
            if number <= 8
            else "9-12"
        )
        original_standards = json.loads((ROOT / route["standards"]).read_bytes())
        standards = {k: v for k, v in original_standards.items() if k != "by_genre"}
        standards["standards"] = original_standards["by_genre"][genre]
        rubric = copy.deepcopy(template)
        rubric["grades"] = ["K" if number == 0 else number]
        rubric["genres"] = [genre]
        rubric["genre_overlay"] = rubric.pop("genre_overlays")[genre]
        rubric["genre_overlay"].update(
            rubric.pop("grade_genre_overrides")[grade].get(genre, {})
        )
        source = rubric["optional_dimensions"]["source_use"]
        source["grade_guidance"] = source["grade_guidance"][band]
        path = ROOT / "grades" / f"grade-{grade[3:]}.json"
        document = documents.setdefault(
            path,
            {
                "id": "project-writing-v1",
                "grade": grade,
                "description": "Self-contained grade rubric. Runtime selects one of the three genres in this file.",
                "rubrics": {},
            },
        )
        document["rubrics"][genre] = {"rubric": rubric, "standards": standards}
    return documents


def main() -> None:
    """Generate or verify the finalized grade-specific rubric JSON files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Check generated files without writing."
    )
    args = parser.parse_args()
    for path, document in grade_documents().items():
        data = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        if args.check:
            if not path.exists() or path.read_text() != data:
                raise SystemExit(
                    f"Grade file differs from the authoring template: {path}"
                )
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data)
    print(
        "Verified 13 grade files."
        if args.check
        else "Wrote 13 grade files, containing 39 complete rubric selections."
    )


if __name__ == "__main__":
    main()

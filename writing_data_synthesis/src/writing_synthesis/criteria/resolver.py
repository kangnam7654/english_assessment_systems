"""Explicit grade/genre routing; unsupported combinations never fall back."""

import hashlib
import json

from writing_synthesis.criteria.catalog import ROOT, select_route
from writing_synthesis.schemas.provenance import CriteriaReference


class ResolvedCriteria:
    """One selected grade/genre, its prompt inputs and reproducibility metadata."""

    def __init__(self, grade: str, genre: str, rubric_id: str | None = None):
        """Resolve one route and load its finalized grade or source-specific profile.

        Args:
            grade: Requested US grade identifier, from us_K through us_12.
            genre: Requested writing genre.
            rubric_id: Explicit rubric identifier, or None to use the route default.
        """
        route = select_route(grade, genre, rubric_id)
        self.grade = grade
        self.genre = genre
        self.grade_file_sha256 = None
        if rubric_id == "project-writing-v1":
            self._load_project_grade(rubric_id)
        else:
            self._load_source_profile(route)

    def _load_project_grade(self, rubric_id: str) -> None:
        """Read one finalized grade file, validating identity before selecting a genre.

        Args:
            rubric_id: Explicit rubric identifier, or None to use the route default.

        Raises:
            ValueError: Grade rubric identity mismatch; Grade rubric scope mismatch.
        """
        grade, genre = self.grade, self.genre
        path = ROOT / "grades" / f"grade-{grade.removeprefix('us_')}.json"
        grade_bytes = path.read_bytes()
        document = json.loads(grade_bytes)
        if document["grade"] != grade or document["id"] != rubric_id:
            raise ValueError("Grade rubric identity mismatch.")
        selected = document["rubrics"][genre]
        self.rubric = selected["rubric"]
        self.standards = selected["standards"]
        if (
            self.rubric["id"] != rubric_id
            or self.rubric["genres"] != [genre]
            or [str(g) for g in self.rubric["grades"]] != [grade.removeprefix("us_")]
        ):
            raise ValueError("Grade rubric scope mismatch.")
        # Capture the selected contents separately from the whole grade file.
        self.rubric_bytes = json.dumps(
            self.rubric, ensure_ascii=False, sort_keys=True
        ).encode()
        self.standards_bytes = json.dumps(
            self.standards, ensure_ascii=False, sort_keys=True
        ).encode()
        self.grade_file_sha256 = hashlib.sha256(grade_bytes).hexdigest()

    def _load_source_profile(self, route: dict) -> None:
        """Preserve provider-specific contracts for older and explicit source requests.

        Args:
            route: Selected catalog route with relative resource paths.
        """
        self.standards_bytes = (ROOT / route["standards"]).read_bytes()
        self.rubric_bytes = (ROOT / route["rubric"]).read_bytes()
        standards = json.loads(self.standards_bytes)
        self.standards = {k: v for k, v in standards.items() if k != "by_genre"}
        self.standards["standards"] = standards["by_genre"][self.genre]
        self.rubric = json.loads(self.rubric_bytes)

    def reference(self, role: str) -> CriteriaReference:
        """Snapshot the selected rubric and standards provenance for one agent role.

        Args:
            role: Agent role receiving the prompt: student or assessor.

        Returns:
            Versioned rubric and standards reference for the supplied role.

        Raises:
            ValueError: Project rubric crosswalk hash mismatch.
        """
        project = self.rubric.get("assessment_kind") == "project"
        urls = (
            [s["source_url"] for s in self.rubric["sources"]]
            if project
            else [self.rubric["source_url"]]
        )
        crosswalk_hash = None
        if project:
            crosswalk_hash = hashlib.sha256(
                (ROOT / self.rubric["crosswalk_file"]).read_bytes()
            ).hexdigest()
            if crosswalk_hash != self.rubric["crosswalk_sha256"]:
                raise ValueError("Project rubric crosswalk hash mismatch.")
        return CriteriaReference(
            role=role,
            grade=self.grade,
            rubric_id=self.rubric["id"],
            rubric_version=self.rubric["adaptation_version"],
            rubric_sha256=hashlib.sha256(self.rubric_bytes).hexdigest(),
            standards_sha256=hashlib.sha256(self.standards_bytes).hexdigest(),
            standard_ids=tuple(self.standards["standards"]),
            source_urls=tuple(dict.fromkeys([self.standards["source_url"], *urls])),
            crosswalk_sha256=crosswalk_hash,
            grade_file_sha256=self.grade_file_sha256,
            source_kind="project_synthesis"
            if project
            else "official_source_adaptation",
        )

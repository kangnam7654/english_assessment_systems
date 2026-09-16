"""Common-rubric contracts: scope, independent scoring, N/A, provenance and storage."""

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from pydantic import ValidationError
from writing_synthesis.app import create_app
from writing_synthesis.cli.catalog_smoke import example_request
from writing_synthesis.criteria.catalog import ROOT, available_routes, load_rubric
from writing_synthesis.llm.mock import MockLLM
from writing_synthesis.schemas.project_assessment import (
    ProjectAssessment,
    ProjectJudgment,
    display_score,
)
from writing_synthesis.schemas.request import WorkflowRequest
from writing_synthesis.schemas.run import WorkflowState
from writing_synthesis.storage.sqlite import SQLiteRunStore
from writing_synthesis.workflows.runner import WorkflowExecutionError, WritingWorkflow

from tests.integration.test_workflow import StubLLM


class ProjectRubricTests(unittest.TestCase):
    """Exercise project rubric tests behavior with controlled fixtures."""
    def setUp(self):
        """Create isolated fixtures and register cleanup for this test scope."""
        self.options = available_routes("project")
        self.workflow = WritingWorkflow(MockLLM())

    def request(self, grade="us_6", genre="argumentative", **changes):
        """Build or submit the request used by this test scenario.

        Args:
            grade: Requested US grade identifier, from us_K through us_12.
            genre: Requested writing genre.
            **changes: Fixture fields to replace for this scenario.

        Returns:
            Request payload or test response used by this scenario.
        """
        option = next(
            o for o in self.options if o["grade"] == grade and o["genre"] == genre
        )
        return WorkflowRequest.model_validate(
            {**example_request(option, "assessment"), **changes}
        )

    def judgment(self, request=None):
        """Construct project judgment fields for the supplied test request.

        Args:
            request: Validated writing request or HTTP request supplying app-scoped
                resources.

        Returns:
            Synthetic raw project judgment for the supplied request.
        """
        assessment = self.workflow.run(request or self.request()).assessed_content
        return {
            k: v
            for k, v in assessment.model_dump().items()
            if k in ProjectJudgment.model_fields
        }

    def test_crosswalk_covers_every_source_dimension_with_matching_hashes(self):
        """Verify crosswalk covers every source dimension with matching hashes."""
        rubric = load_rubric("project-writing-v1")
        crosswalk_bytes = (ROOT / rubric["crosswalk_file"]).read_bytes()
        self.assertEqual(
            hashlib.sha256(crosswalk_bytes).hexdigest(), rubric["crosswalk_sha256"]
        )
        crosswalk = json.loads(crosswalk_bytes)
        source_ids = {o["rubric_id"] for o in available_routes()}
        expected = {
            (rid, d) for rid in source_ids for d in load_rubric(rid)["score_ranges"]
        }
        actual = {
            (r["source_rubric_id"], r["source_dimension"])
            for r in crosswalk["mappings"]
        }
        self.assertEqual(expected, actual)
        self.assertEqual(len(actual), len(crosswalk["mappings"]))
        self.assertEqual({s["rubric_id"] for s in rubric["sources"]}, source_ids)
        self.assertEqual(len(source_ids), 16)
        for row in crosswalk["mappings"]:
            original = load_rubric(row["source_rubric_id"])
            self.assertEqual(row["source_sha256"], original["source_sha256"])
            self.assertEqual(
                row["source_range"], original["score_ranges"][row["source_dimension"]]
            )
            self.assertFalse(row["numeric_conversion"])

    def test_all_39_routes_modes_and_levels_round_trip_with_selected_prompts(self):
        """Verify all 39 routes modes and levels round trip with selected prompts."""
        self.assertEqual(len(self.options), 39)
        pairs = {(o["grade"], o["genre"]) for o in self.options}
        expected = {
            (f"us_{g}", genre)
            for g in ["K", *range(1, 13)]
            for genre in (
                "opinion" if g == "K" or g < 6 else "argumentative",
                "informative",
                "narrative",
            )
        }
        self.assertEqual(pairs, expected)
        count = 0
        for option in self.options:
            for mode in ("synthesis", "assessment"):
                for level in ("beginner", "intermediate", "advanced", "master"):
                    with self.subTest(
                        grade=option["grade"],
                        genre=option["genre"],
                        mode=mode,
                        level=level,
                    ):
                        request = WorkflowRequest.model_validate(
                            example_request(option, mode, level)
                        )
                        state = self.workflow.run(request)
                        result = state.assessed_content
                        self.assertIsInstance(result, ProjectAssessment)
                        self.assertEqual(result.normalized_scores.task_content, 66.67)
                        self.assertEqual(
                            result.source_use_applicable,
                            option["genre"] == "argumentative",
                        )
                        self.assertNotIn("total_score", result.model_dump())
                        self.assertEqual(
                            WorkflowState.model_validate_json(state.model_dump_json()),
                            state,
                        )
                        assessor = next(
                            p.system_prompt
                            for p in state.prompts
                            if p.role == "assessor"
                        )
                        self.assertNotIn("Target level:", assessor)
                        if mode == "synthesis":
                            student = next(
                                p.system_prompt
                                for p in state.prompts
                                if p.role == "student"
                            )
                            self.assertIn(f"Target level: {level}", student)
                            self.assertNotIn("Score source_use independently", student)
                            self.assertNotIn("source_use must be null", student)
                        self.assertNotIn("grade_genre_overrides", assessor)
                        self.assertNotIn("by_genre", assessor)
                        context = json.loads(assessor.splitlines()[-1])
                        self.assertNotIn("genre_overlays", context)
                        self.assertIn("genre_overlay", context)
                        band = request.grade_for_assessor[3:]
                        band = (
                            "9-10"
                            if band in {"9", "10"}
                            else "11-12"
                            if band in {"11", "12"}
                            else band
                        )
                        self.assertTrue(
                            all(
                                f".{band}." in sid
                                for sid in context["standards"]["standards"]
                            )
                        )
                        ref = state.criteria[0]
                        self.assertEqual(ref.source_kind, "project_synthesis")
                        self.assertIsNotNone(ref.crosswalk_sha256)
                        self.assertEqual(len(ref.source_urls), 17)
                        if (
                            request.grade_for_assessor == "us_6"
                            and request.genre == "argumentative"
                        ):
                            self.assertIn("Counterclaims are not required.", assessor)
                        count += 1
        self.assertEqual(count, 312)

    def test_optional_sources_are_scored_or_null_never_zero(self):
        """Verify optional sources are scored or null never zero."""
        sources = [
            {
                "source_id": "fixture",
                "text": "Fictional source for contract verification.",
            }
        ]
        for genre in ("opinion", "informative", "narrative"):
            for passages in ([], sources):
                request = self.request("us_2", genre, source_passages=passages)
                result = self.workflow.run(request).assessed_content
                applies = bool(passages) and genre != "narrative"
                self.assertEqual(result.source_use_applicable, applies)
                self.assertEqual(
                    result.source_use_status, "scored" if applies else "not_applicable"
                )
                self.assertEqual(
                    result.source_use_normalized, 66.67 if applies else None
                )
                raw = self.judgment(request)
                raw["source_use"] = (
                    None if applies else raw["per_criterion"]["conventions"]
                )
                with self.assertRaises(ValueError):
                    ProjectAssessment.from_judgment(
                        ProjectJudgment.model_validate(raw),
                        source_use_applicable=applies,
                    )
        with self.assertRaises(ValidationError):
            self.request(source_passages=[])

    def test_raw_score_contract_and_application_normalization(self):
        """Verify raw score contract and application normalization."""
        raw = self.judgment()
        for score, expected in ((1, 0), (2, 33.33), (3, 66.67), (4, 100)):
            body = copy.deepcopy(raw)
            for dimension in body["per_criterion"].values():
                dimension["score"] = score
            body["source_use"]["score"] = score
            result = ProjectAssessment.from_judgment(
                ProjectJudgment.model_validate(body), source_use_applicable=True
            )
            self.assertEqual(
                set(result.normalized_scores.model_dump().values()), {expected}
            )
            self.assertEqual(result.source_use_normalized, expected)
        for bad in (0, 5, True, "3", 2.5, float("nan")):
            body = copy.deepcopy(raw)
            body["per_criterion"]["conventions"]["score"] = bad
            with self.assertRaises(ValidationError):
                ProjectJudgment.model_validate(body)
            with self.assertRaises(ValueError):
                display_score(bad)
        for mutate in (
            lambda b: b["per_criterion"].pop("organization"),
            lambda b: b["per_criterion"].update(extra=b["source_use"]),
            lambda b: b.update(total_score=12),
            lambda b: b.update(normalized_scores={"conventions": 100}),
        ):
            body = copy.deepcopy(raw)
            mutate(body)
            with self.assertRaises(ValidationError):
                ProjectJudgment.model_validate(body)
        result = self.workflow.run(self.request()).assessed_content
        for change in (
            {
                "normalized_scores": {
                    **result.normalized_scores.model_dump(),
                    "conventions": 100,
                }
            },
            {"source_use_status": "not_applicable"},
            {"source_use_normalized": 0},
            {"source_use_applicable": False},
        ):
            with self.assertRaises(ValidationError):
                ProjectAssessment.model_validate({**result.model_dump(), **change})

    def test_not_scorable_and_source_applicability_survive_storage(self):
        """Verify not scorable and source applicability survive storage."""
        for request in (self.request(), self.request("us_K", "narrative")):
            raw = self.judgment(request)
            raw.update(status="not_scorable", per_criterion=None, source_use=None)
            for reason in ("insufficient_text", "non_english"):
                raw["not_scorable_reason"] = reason
                state = WritingWorkflow(StubLLM([raw])).run(request)
                result = state.assessed_content
                self.assertIsNone(result.normalized_scores)
                self.assertIsNone(result.source_use_normalized)
                self.assertEqual(
                    result.source_use_status,
                    "not_scorable" if request.source_passages else "not_applicable",
                )
                self.assertEqual(
                    WorkflowState.model_validate_json(state.model_dump_json()), state
                )
            raw["not_scorable_reason"] = "off_topic"
            with self.assertRaises(ValidationError):
                ProjectJudgment.model_validate(raw)

    def test_api_persistence_and_rejection_of_wrong_identity_and_scores(self):
        """Verify api persistence and rejection of wrong identity and scores."""
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "runs.sqlite3"
            store = SQLiteRunStore(database)
            with TestClient(create_app(WritingWorkflow(MockLLM(), store))) as client:
                self.assertEqual(len(client.get("/criteria?family=project").json()), 39)
                self.assertEqual(len(client.get("/criteria").json()), 45)
                self.assertEqual(
                    client.get("/criteria?family=unknown").status_code, 422
                )
                response = client.post(
                    "/run", json=self.request().model_dump(mode="json")
                )
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                detail = client.get(f"/runs/{result['run_id']}").json()
                self.assertEqual(result["assessed_content"], detail["assessed_content"])
            state = SQLiteRunStore(database).get(UUID(result["run_id"]))
            self.assertEqual(
                state.assessed_content.normalized_scores.conventions, 66.67
            )
        raw = self.judgment()
        for change in (
            {"grade": "us_7"},
            {"genre": "informative"},
            {"source_use": None},
            {"total_score": 12},
        ):
            with self.assertRaises(WorkflowExecutionError) as failure:
                WritingWorkflow(StubLLM([{**raw, **change}])).run(self.request())
            self.assertEqual(failure.exception.state.error.code, "invalid_output")
            self.assertEqual(failure.exception.state.stage, "failed")

    def test_persisted_applicability_cannot_drift_from_task(self):
        """Verify persisted applicability cannot drift from task."""
        request = self.request("us_2", "informative")
        state = self.workflow.run(request).model_dump()
        state["request"]["source_passages"] = [
            {"source_id": "new", "text": "New source."}
        ]
        with self.assertRaises(ValidationError):
            WorkflowState.model_validate(state)

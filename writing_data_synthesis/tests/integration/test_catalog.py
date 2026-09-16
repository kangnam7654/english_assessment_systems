"""Independent coverage expectations plus every routed model/API score contract."""

import copy
import hashlib
import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import ValidationError
from writing_synthesis.app import create_app
from writing_synthesis.cli.catalog_smoke import example_request
from writing_synthesis.criteria.catalog import (
    ROOT,
    available_routes,
    load_rubric,
    select_route,
)
from writing_synthesis.criteria.output_schema import assessment_output_schema
from writing_synthesis.criteria.resolver import ResolvedCriteria
from writing_synthesis.llm.mock import MockLLM
from writing_synthesis.schemas.assessment import (
    ArgumentativeAssessment,
    SourceAssessment,
)
from writing_synthesis.schemas.request import WorkflowRequest
from writing_synthesis.schemas.run import WorkflowState
from writing_synthesis.workflows.runner import WorkflowExecutionError, WritingWorkflow

from tests.integration.test_workflow import StubLLM


class CatalogTests(unittest.TestCase):
    """Exercise catalog tests behavior with controlled fixtures."""
    def setUp(self):
        """Create isolated fixtures and register cleanup for this test scope."""
        self.options = available_routes()

    def test_complete_collected_rubric_coverage_and_default_matrix(self):
        """Verify complete collected rubric coverage and default matrix."""
        self.assertEqual(len(self.options), 45)
        defaults = {
            (o["grade"], o["genre"]): o for o in self.options if o["is_default"]
        }
        self.assertEqual(len(defaults), 39)
        for grade in ["K", *range(1, 13)]:
            genres = (
                "opinion" if grade == "K" or grade < 6 else "argumentative",
                "informative",
                "narrative",
            )
            for genre in genres:
                self.assertIn((f"us_{grade}", genre), defaults)
        sources = json.loads(
            (ROOT.parent / "docs/rubric-evidence/sources.json").read_text()
        )["sources"]
        expected_hashes = {s["sha256"] for s in sources if s["id"] != "ccss-ela-2010"}
        rubrics = {o["rubric_id"]: load_rubric(o["rubric_id"]) for o in self.options}
        self.assertEqual(len(rubrics), 16)
        self.assertEqual(
            {r["source_sha256"] for r in rubrics.values()}, expected_hashes
        )
        for rubric in rubrics.values():
            for name, (low, high) in rubric["score_ranges"].items():
                self.assertEqual(
                    set(rubric["dimensions"][name]),
                    {str(s) for s in range(low, high + 1)},
                )
                self.assertTrue(
                    all(text.strip() for text in rubric["dimensions"][name].values())
                )
        # Source-specific scales are not all coerced into the same 10-point scale.
        for option in self.options:
            scales = option["score_ranges"]
            if option["rubric_id"].startswith("uen-"):
                self.assertEqual(
                    scales, {"focus_organization": [1, 4], "conventions": [0, 2]}
                )
            elif option["rubric_id"].startswith("oregon-"):
                self.assertEqual(
                    len(scales), 6 if option["genre"] == "narrative" else 7
                )
                self.assertTrue(all(scale == [1, 6] for scale in scales.values()))
                if option["genre"] != "narrative":
                    self.assertIn("use_of_sources", scales)
            else:
                self.assertEqual(len(scales), 3)
                self.assertEqual(scales["conventions"], [0, 2])

    def test_every_provider_grade_mode_and_level_executes_and_round_trips(self):
        """Verify every provider grade mode and level executes and round trips."""
        runner = WritingWorkflow(MockLLM())
        count = 0
        for option in self.options:
            for mode in ("synthesis", "assessment"):
                for level in ("beginner", "intermediate", "advanced", "master"):
                    with self.subTest(
                        option=option["rubric_id"],
                        grade=option["grade"],
                        mode=mode,
                        level=level,
                    ):
                        request = WorkflowRequest.model_validate(
                            example_request(option, mode, level)
                        )
                        state = runner.run(request)
                        self.assertEqual(state.stage, "completed")
                        self.assertEqual(
                            state.assessed_content.rubric_id, option["rubric_id"]
                        )
                        self.assertEqual(state.model.execution_mode, "mock")
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
                        if mode == "assessment":
                            self.assertEqual(state.essay, request.essay)
                            self.assertNotIn("generating", state.history)
                        count += 1
        self.assertEqual(count, 360)

    def test_all_rubric_score_boundaries_missing_extra_and_ns_reasons(self):
        """Verify all rubric score boundaries missing extra and ns reasons."""
        options = {o["rubric_id"]: o for o in self.options}.values()
        for option in options:
            original = (
                WritingWorkflow(MockLLM())
                .run(WorkflowRequest.model_validate(example_request(option)))
                .assessed_content.model_dump()
            )
            for extreme in (0, 1):
                body = copy.deepcopy(original)
                for name, bounds in option["score_ranges"].items():
                    body["per_criterion"][name]["score"] = bounds[extreme]
                body["total_score"] = sum(
                    d["score"] for d in body["per_criterion"].values()
                )
                SourceAssessment.model_validate(body)
            for name, (low, high) in option["score_ranges"].items():
                for bad in (low - 1, high + 1, True, "2", 2.5):
                    body = copy.deepcopy(original)
                    body["per_criterion"][name]["score"] = bad
                    with (
                        self.subTest(rubric=option["rubric_id"], name=name, bad=bad),
                        self.assertRaises(ValidationError),
                    ):
                        SourceAssessment.model_validate(body)
            body = copy.deepcopy(original)
            del body["per_criterion"][next(iter(body["per_criterion"]))]
            with self.assertRaises(ValidationError):
                SourceAssessment.model_validate(body)
            body = copy.deepcopy(original)
            body["per_criterion"]["unexpected"] = next(
                iter(body["per_criterion"].values())
            )
            with self.assertRaises(ValidationError):
                SourceAssessment.model_validate(body)
            with self.assertRaises(ValidationError):
                SourceAssessment.model_validate(
                    {**original, "total_score": original["total_score"] + 1}
                )
            ns = {
                **original,
                "status": "not_scorable",
                "per_criterion": None,
                "total_score": None,
            }
            for reason in option["not_scorable_reasons"]:
                SourceAssessment.model_validate({**ns, "not_scorable_reason": reason})
            with self.assertRaises(ValidationError):
                SourceAssessment.model_validate(
                    {**ns, "not_scorable_reason": "unsupported"}
                )

    def test_selected_prompt_schema_and_provenance_only_use_requested_criteria(self):
        """Verify selected prompt schema and provenance only use requested criteria."""
        for option in self.options:
            criteria = ResolvedCriteria(
                option["grade"], option["genre"], option["rubric_id"]
            )
            schema = assessment_output_schema(criteria)
            self.assertEqual(
                set(schema["properties"]["per_criterion"]["anyOf"][0]["properties"]),
                set(option["score_ranges"]),
            )
            self.assertEqual(
                schema["properties"]["rubric_id"]["const"], option["rubric_id"]
            )
            ref = criteria.reference("assessor")
            self.assertEqual(
                ref.rubric_sha256, hashlib.sha256(criteria.rubric_bytes).hexdigest()
            )
            self.assertEqual(
                ref.standards_sha256,
                hashlib.sha256(criteria.standards_bytes).hexdigest(),
            )
            band = option["grade"].removeprefix("us_")
            if band in {"9", "10"}:
                band = "9-10"
            if band in {"11", "12"}:
                band = "11-12"
            self.assertTrue(all(f".{band}." in sid for sid in ref.standard_ids))
            writing = [sid for sid in ref.standard_ids if ".W." in sid]
            expected = {
                "opinion": "1",
                "argumentative": "1",
                "informative": "2",
                "narrative": "3",
            }[option["genre"]]
            self.assertTrue(all(f".W.{band}.{expected}" in sid for sid in writing))
            self.assertTrue(writing)

    def test_source_requirements_and_provider_scope_are_enforced_before_calls(self):
        """Verify source requirements and provider scope are enforced before calls."""
        llm = StubLLM([])
        with TestClient(create_app(WritingWorkflow(llm))) as client:
            for option in self.options:
                body = example_request(option)
                body.pop("source_passages", None)
                if option["requires_sources"]:
                    self.assertEqual(client.post("/run", json=body).status_code, 422)
                else:
                    WorkflowRequest.model_validate(body)
            base = example_request(
                next(
                    o
                    for o in self.options
                    if o["grade"] == "us_6" and o["genre"] == "argumentative"
                )
            )
            for changes in (
                {"rubric_id": "../secret"},
                {"rubric_id": "oregon-hs-narrative-summary-v1"},
                {"grade_for_student": "us_5"},
                {"genre": "essay"},
                {"grade_for_assessor": "us_13"},
            ):
                self.assertEqual(
                    client.post("/run", json={**base, **changes}).status_code, 422
                )
        self.assertEqual(llm.calls, [])

    def test_supported_provider_output_still_must_match_the_selected_provider(self):
        """Verify supported provider output still must match the selected provider."""
        alternatives = [
            o
            for o in self.options
            if o["grade"] == "us_9" and o["genre"] == "argumentative"
        ]
        default = next(o for o in alternatives if o["is_default"])
        other = next(o for o in alternatives if not o["is_default"])
        response = (
            WritingWorkflow(MockLLM())
            .run(WorkflowRequest.model_validate(example_request(other, "assessment")))
            .assessed_content.model_dump()
        )
        with self.assertRaises(WorkflowExecutionError) as error:
            WritingWorkflow(StubLLM([response])).run(
                WorkflowRequest.model_validate(example_request(default, "assessment"))
            )
        self.assertEqual(error.exception.state.error.code, "invalid_output")

    def test_discovery_api_and_default_selection(self):
        """Verify discovery api and default selection."""
        with TestClient(create_app(WritingWorkflow(MockLLM()))) as client:
            response = client.get("/criteria")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 45)
        for option in self.options:
            if option["is_default"]:
                selected = select_route(option["grade"], option["genre"])
                self.assertEqual(Path(selected["rubric"]).stem, option["rubric_id"])
        self.assertNotIn(str(ROOT), response.text)

    def test_original_grade_six_score_contract_remains_readable(self):
        """Verify original grade six score contract remains readable."""
        feedback = {"comment_english": "Mock", "comment_korean": "Mock"}
        old = ArgumentativeAssessment.model_validate(
            {
                "rubric_id": "sb-argumentative-summary-v1",
                "grade": "us_6",
                "status": "scored",
                "per_criterion": {
                    name: {"score": score, **feedback}
                    for name, score in (
                        ("organization_purpose", 3),
                        ("evidence_elaboration", 3),
                        ("conventions", 2),
                    )
                },
                "total_score": 8,
                "not_scorable_reason": None,
                "summary_feedback_english": "Mock",
                "summary_feedback_korean": "Mock",
            }
        )
        self.assertEqual(old.total_score, 8)
        self.assertTrue(
            (
                ROOT.parent
                / "docs/rubric-evidence/source-rubrics/sb-argumentative-summary-v1.json"
            ).is_file()
        )

    def test_source_result_dimensions_are_immutable(self):
        """Verify source result dimensions are immutable."""
        result = (
            WritingWorkflow(MockLLM())
            .run(WorkflowRequest.model_validate(example_request(self.options[0])))
            .assessed_content
        )
        with self.assertRaises(ValidationError):
            result.per_criterion.conventions.score = 99

"""Validation boundaries and durable JSON shape, without a database or live LLM."""

import copy
import hashlib
import json
import unittest
from uuid import UUID

import writing_synthesis.app as api
from fastapi.testclient import TestClient
from pydantic import ValidationError
from writing_synthesis.schemas.assessment import SourceAssessment
from writing_synthesis.schemas.provenance import ModelSnapshot
from writing_synthesis.schemas.request import WorkflowRequest
from writing_synthesis.schemas.run import Stage, WorkflowState
from writing_synthesis.workflows.runner import WorkflowExecutionError, WritingWorkflow

from tests.fixtures import assessment
from tests.integration.test_workflow import StubLLM


class SchemaTests(unittest.TestCase):
    """Exercise schema tests behavior with controlled fixtures."""
    def run_example(self, **request):
        """Run a deterministic writing example for schema round-trip assertions.

        Args:
            **request: Validated writing request or HTTP request supplying app-scoped
                resources.

        Returns:
            Completed deterministic workflow state used for schema checks.
        """
        return WritingWorkflow(
            StubLLM(
                [
                    {"essay_english": "A short essay."},
                    assessment(),
                ]
            )
        ).run(WorkflowRequest(user_prompt="A hobby", **request))

    def test_completed_state_round_trip_and_provenance(self):
        """Verify completed state round trip and provenance."""
        state = self.run_example()
        restored = WorkflowState.model_validate_json(state.model_dump_json())
        self.assertEqual(restored, state)
        self.assertEqual(restored.schema_version, "1.0")
        self.assertIsInstance(restored.run_id, UUID)
        self.assertIsNotNone(restored.finished_at)
        self.assertEqual(restored.attempts[0].word_count, 3)
        self.assertEqual(restored.attempts[0].assessment, restored.assessed_content)
        self.assertEqual(
            {r.source_kind for r in restored.criteria}, {"official_source_adaptation"}
        )
        self.assertTrue(all(r.standard_ids for r in restored.criteria))
        for prompt in restored.prompts:
            self.assertEqual(
                prompt.sha256, hashlib.sha256(prompt.system_prompt.encode()).hexdigest()
            )
        with self.assertRaises(ValidationError):
            restored.stage = Stage.PENDING
        with self.assertRaises(ValidationError):
            restored.request.level = "master"
        history = restored.history
        history.clear()
        self.assertEqual(restored.stage, restored.events[-1].stage)

    def test_failure_round_trip_retains_work_without_raw_error(self):
        """Verify failure round trip retains work without raw error."""
        runner = WritingWorkflow(
            StubLLM(
                [
                    {"essay_english": "An existing draft."},
                    RuntimeError("private-token-value"),
                ]
            )
        )
        with self.assertRaises(WorkflowExecutionError) as raised:
            runner.run(WorkflowRequest(user_prompt="A hobby"))
        state = raised.exception.state
        serialized = state.model_dump_json()
        self.assertNotIn("private-token-value", serialized)
        restored = WorkflowState.model_validate_json(serialized)
        self.assertEqual(restored.essay, "An existing draft.")
        self.assertEqual(restored.error.code, "model_call_failed")
        self.assertEqual(restored.failed_stage, Stage.ASSESSING)
        self.assertIsNotNone(restored.finished_at)
        self.assertIsNone(restored.assessed_content)

    def test_rejects_malformed_assessment_payloads(self):
        """Verify rejects malformed assessment payloads."""
        cases = []
        for score in [-1, 101, float("nan"), float("inf"), "60", True]:
            cases.append({**assessment(), "total_score": score})
        for score in [-1, 6, "3", True, float("nan")]:
            body = assessment()
            body["per_criterion"]["organization_purpose"]["score"] = score
            cases.append(body)
        for field in assessment():
            if field == "schema_version":
                continue
            body = assessment()
            del body[field]
            cases.append(body)
        for extra in ["extra", "api_key"]:
            cases.append({**assessment(), extra: "ignored?"})
        body = assessment()
        del body["per_criterion"]["conventions"]
        cases.append(body)
        body = assessment()
        body["per_criterion"]["unsupported"] = body["per_criterion"][
            "organization_purpose"
        ]
        cases.append(body)
        cases.extend(
            [
                {**assessment(), "grade": "grade_6"},
                {**assessment(), "level": "unknown"},
                {**assessment(), "summary_feedback_english": " "},
            ]
        )
        for body in cases:
            with self.subTest(body=body), self.assertRaises(ValidationError):
                SourceAssessment.model_validate(body)

    def test_invalid_output_fails_workflow_and_http_with_run_id(self):
        """Verify invalid output fails workflow and http with run id."""
        for body in [{"total_score": 999}, assessment(grade="us_7")]:
            llm = StubLLM([body])
            with (
                TestClient(api.create_app(WritingWorkflow(llm))) as client,
                self.assertLogs("writing_synthesis.api.routes", level="ERROR"),
            ):
                response = client.post(
                    "/run",
                    json={
                        "mode": "assessment",
                        "user_prompt": "A hobby",
                        "essay": "A draft",
                    },
                )
            self.assertEqual(response.status_code, 500)
            detail = response.json()["detail"]
            self.assertIsInstance(UUID(detail["run_id"]), UUID)
            self.assertEqual(detail["failed_stage"], "assessing")
            self.assertEqual(detail["code"], "invalid_output")
            self.assertNotIn("essay", detail)

    def test_task_context_reaches_both_agents_without_target_leakage(self):
        """Verify task context reaches both agents without target leakage."""
        llm = StubLLM(
            [{"essay_english": "A draft."}, assessment(genre="argumentative")]
        )
        state = WritingWorkflow(llm).run(
            WorkflowRequest(
                user_prompt="Discuss the passage",
                genre="argumentative",
                level="master",
                source_passages=[
                    {"source_id": "source-1", "text": "Public transport saves space."}
                ],
            )
        )
        generator_task = json.loads(llm.calls[0][1]["content"])
        assessor_task = json.loads(json.loads(llm.calls[1][1]["content"])["assignment"])
        self.assertEqual(generator_task, assessor_task)
        self.assertEqual(generator_task["genre"], "argumentative")
        self.assertEqual(generator_task["source_passages"][0]["source_id"], "source-1")
        self.assertNotIn("level", generator_task)
        self.assertNotIn("Target level:", llm.calls[1][0]["content"])
        self.assertEqual(state.request.level, "master")

    def test_unknown_request_fields_and_duplicate_sources_are_rejected(self):
        """Verify unknown request fields and duplicate sources are rejected."""
        for fields in [
            {"genre": "unknown"},
            {"grade_for_student": 6},
            {"extra": True},
            {"schema_version": "2.0"},
            {
                "source_passages": [
                    {"source_id": "same", "text": "A"},
                    {"source_id": "same", "text": "B"},
                ]
            },
        ]:
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                WorkflowRequest(user_prompt="Topic", **fields)
        with TestClient(api.create_app(WritingWorkflow(StubLLM([])))) as client:
            response = client.post("/run", json={"user_prompt": "Topic", "unknown": 1})
        self.assertEqual(response.status_code, 422)

    def test_tampered_run_records_are_rejected(self):
        """Verify tampered run records are rejected."""
        original = self.run_example().model_dump(mode="json")
        changes = []
        body = copy.deepcopy(original)
        body["schema_version"] = "2.0"
        changes.append(body)
        body = copy.deepcopy(original)
        body["finished_at"] = None
        changes.append(body)
        body = copy.deepcopy(original)
        body["attempts"][0]["assessment"] = None
        changes.append(body)
        body = copy.deepcopy(original)
        body["attempts"][0]["word_count"] = 200
        changes.append(body)
        body = copy.deepcopy(original)
        body["attempts"][0]["number"] = 2
        changes.append(body)
        body = copy.deepcopy(original)
        body["events"][1]["stage"] = "completed"
        changes.append(body)
        body = copy.deepcopy(original)
        body["criteria"] = []
        changes.append(body)
        body = copy.deepcopy(original)
        body["prompts"][0]["system_prompt"] += " changed"
        changes.append(body)
        for body in changes:
            with self.subTest(body=body), self.assertRaises(ValidationError):
                WorkflowState.model_validate(body)

    def test_model_metadata_is_an_explicit_allowlist(self):
        """Verify model metadata is an explicit allowlist."""
        with self.assertRaises(ValidationError):
            ModelSnapshot(adapter="example", api_key="secret")

    def test_assessment_only_retains_original_essay_and_metadata(self):
        """Verify assessment only retains original essay and metadata."""
        runner = WritingWorkflow(StubLLM([assessment()]))
        state = runner.run(
            WorkflowRequest(
                mode="assessment", user_prompt="A hobby", essay="Original text."
            )
        )
        self.assertEqual(state.attempts[0].origin, "provided")
        self.assertEqual([p.role for p in state.prompts], ["assessor"])
        self.assertNotIn(Stage.GENERATING, state.history)
        self.assertEqual(
            WorkflowState.model_validate_json(state.model_dump_json()).essay,
            "Original text.",
        )

    def test_openapi_exposes_nested_validation_contract(self):
        """Verify openapi exposes nested validation contract."""
        schema = api.app.openapi()["components"]["schemas"]
        self.assertIn("WorkflowRequest", schema)
        self.assertIn("SourceAssessment", schema)
        self.assertIn("NarrativeCriteria", schema)
        self.assertIn("FailedRunResponse", schema)
        self.assertFalse(schema["SourceAssessment"]["additionalProperties"])

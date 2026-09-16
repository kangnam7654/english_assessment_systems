"""Durability, source routing and API behavior with no live model connections."""

import copy
import json
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import writing_synthesis.app as api
from fastapi.testclient import TestClient
from pydantic import ValidationError
from writing_synthesis.llm.mock import MockLLM
from writing_synthesis.schemas.assessment import SourceAssessment
from writing_synthesis.schemas.request import WorkflowRequest
from writing_synthesis.schemas.run import Stage, WorkflowState
from writing_synthesis.storage.base import StorageError
from writing_synthesis.storage.sqlite import SQLiteRunStore
from writing_synthesis.workflows.runner import WorkflowExecutionError, WritingWorkflow

from tests.fixtures import SOURCE_REQUEST, assessment
from tests.integration.test_workflow import StubLLM


class PersistenceTests(unittest.TestCase):
    """Exercise persistence tests behavior with controlled fixtures."""
    def setUp(self):
        """Create isolated fixtures and register cleanup for this test scope."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "runs.sqlite3"
        self.store = SQLiteRunStore(self.path)
        self.request = WorkflowRequest.model_validate(SOURCE_REQUEST)

    def test_mock_api_lifespan_post_get_and_reopen_without_sdk(self):
        """Verify mock api lifespan post get and reopen without sdk."""
        with (
            patch.dict(
                os.environ, {"WDS_LLM_MODE": "mock", "WDS_DATA_DIR": self.temp.name}
            ),
            patch(
                "writing_synthesis.config.OpenAICompatibleLLM",
                side_effect=AssertionError("Must not connect"),
            ),
            TestClient(api.app) as client,
        ):
            response = client.post("/run", json=SOURCE_REQUEST)
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertEqual(body["execution_mode"], "mock")
            self.assertEqual(body["assessed_content"]["total_score"], 8)
            detail = client.get(f"/runs/{body['run_id']}")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(
                detail.json()["assessed_content"], body["assessed_content"]
            )
            self.assertNotIn("prompts", detail.json())
            self.assertNotIn("model", detail.json())
            self.assertEqual(client.get(f"/runs/{uuid4()}").status_code, 404)
            self.assertEqual(client.get("/runs/bad-id").status_code, 422)
        state = SQLiteRunStore(self.path).get(UUID(body["run_id"]))
        self.assertEqual(state.stage, Stage.COMPLETED)
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute(
                "SELECT revision, state_json FROM run_snapshots ORDER BY revision"
            ).fetchall()
        self.assertEqual([r[0] for r in rows], list(range(6)))
        self.assertEqual(
            [json.loads(r[1])["stage"] for r in rows],
            [
                "pending",
                "preparing",
                "preparing",
                "generating",
                "assessing",
                "completed",
            ],
        )
        with (
            patch.dict(
                os.environ, {"WDS_LLM_MODE": "mock", "WDS_DATA_DIR": self.temp.name}
            ),
            TestClient(api.app) as client,
        ):
            self.assertEqual(
                client.get(f"/runs/{body['run_id']}").json(), detail.json()
            )

    def test_source_provenance_target_isolation_and_assessment_mode(self):
        """Verify source provenance target isolation and assessment mode."""
        class RecordingMock(MockLLM):
            """Exercise recording mock behavior with controlled fixtures."""
            def __init__(self):
                """Initialize the controlled test double and its recorded responses."""
                self.calls = []

            def complete(self, messages):
                """Return a controlled model response and record the supplied messages.

                Args:
                    messages: Ordered role/content messages sent to the chat completion endpoint.

                Returns:
                    Completed assistant text; Mock clients produce deterministic synthetic JSON.
                """
                self.calls.append(messages)
                return super().complete(messages)

        model = RecordingMock()
        state = WritingWorkflow(model, self.store).run(self.request)
        self.assertTrue(
            all(r.source_kind == "official_source_adaptation" for r in state.criteria)
        )
        self.assertTrue(
            all("CCSS.ELA-Literacy.W.6.1.a" in r.standard_ids for r in state.criteria)
        )
        self.assertTrue(all(r.standards_sha256 for r in state.criteria))
        self.assertIn("Target level:", model.calls[0][0]["content"])
        self.assertNotIn("Target level:", model.calls[1][0]["content"])
        self.assertIn(
            "Counterarguments are not required in grade 6", model.calls[1][0]["content"]
        )
        self.assertNotIn(
            "level", json.loads(json.loads(model.calls[1][1]["content"])["assignment"])
        )
        assessment_request = WorkflowRequest.model_validate(
            {**SOURCE_REQUEST, "mode": "assessment", "essay": "Provided essay."}
        )
        result = WritingWorkflow(MockLLM(), self.store).run(assessment_request)
        self.assertEqual(result.essay, "Provided essay.")
        self.assertNotIn(Stage.GENERATING, result.history)

    def test_unsupported_routes_rejected_before_model(self):
        """Verify unsupported routes rejected before model."""
        llm = StubLLM([])
        with (
            TestClient(api.create_app(WritingWorkflow(llm, self.store))) as client,
        ):
            for changes in (
                {"genre": "opinion"},
                {"source_passages": []},
                {"grade_for_student": "mid_2"},
                {"user_prompt": None},
            ):
                self.assertEqual(
                    client.post("/run", json={**SOURCE_REQUEST, **changes}).status_code,
                    422,
                )
        self.assertEqual(llm.calls, [])

    def test_failed_assessment_is_saved_and_queryable_with_partial_essay(self):
        """Verify failed assessment is saved and queryable with partial essay."""
        llm = StubLLM(
            [
                {"essay_english": "A retained essay."},
                RuntimeError("secret-provider-body"),
            ]
        )
        with (
            TestClient(api.create_app(WritingWorkflow(llm, self.store))) as client,
            self.assertLogs("writing_synthesis.api.routes", level="ERROR"),
        ):
            response = client.post("/run", json=SOURCE_REQUEST)
            self.assertEqual(response.status_code, 500)
            detail = client.get(f"/runs/{response.json()['detail']['run_id']}").json()
        self.assertEqual(detail["essay"], "A retained essay.")
        self.assertEqual(detail["stage"], "failed")
        self.assertEqual(detail["error"]["stage"], "assessing")
        self.assertNotIn("secret-provider-body", json.dumps(detail))
        self.assertIsNone(detail["assessed_content"])

    def test_revision_conflicts_and_terminal_immutability(self):
        """Verify revision conflicts and terminal immutability."""
        initial = WorkflowState(request=self.request)
        self.store.save(initial)
        self.store.save(initial)  # Idempotent retry.
        next_state = initial.advance(Stage.PREPARING)
        self.store.save(next_state)
        with self.assertRaises(StorageError):
            self.store.save(initial)
        changed = next_state.evolve(
            request=self.request.model_copy(update={"level": "master"})
        )
        with self.assertRaises(StorageError):
            self.store.save(changed)
        done = WritingWorkflow(MockLLM(), self.store).run(self.request)
        with self.assertRaises(StorageError):
            self.store.save(done.evolve())

    def test_concurrent_runs_have_isolated_durable_results(self):
        """Verify concurrent runs have isolated durable results."""
        runner = WritingWorkflow(MockLLM(), self.store)
        with ThreadPoolExecutor(max_workers=4) as pool:
            states = list(pool.map(runner.run, [self.request] * 8))
        self.assertEqual(len({s.run_id for s in states}), 8)
        for state in states:
            self.assertEqual(self.store.get(state.run_id), state)

    def test_storage_failure_stops_calls_and_returns_503(self):
        """Verify storage failure stops calls and returns 503."""
        class BrokenStore:
            """Exercise broken store behavior with controlled fixtures."""
            def save(self, state):
                """Simulate the persistence behavior required by this failure scenario.

                Args:
                    state: Validated immutable workflow snapshot.
                """
                if state.stage == Stage.ASSESSING:
                    raise StorageError("private-path")

            def get(self, run_id):
                """Return the test store's configured lookup result.

                Args:
                    run_id: Unique identifier of the persisted workflow run.
                """
                raise StorageError("private-path")

        llm = StubLLM([{"essay_english": "Generated essay."}])
        with (
            TestClient(api.create_app(WritingWorkflow(llm, BrokenStore()))) as client,
        ):
            response = client.post("/run", json=SOURCE_REQUEST)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("private-path", response.text)
            self.assertEqual(client.get(f"/runs/{uuid4()}").status_code, 503)
        self.assertEqual(len(llm.calls), 1)

    def test_wrong_genre_output_cannot_satisfy_selected_rubric(self):
        """Verify wrong genre output cannot satisfy selected rubric."""
        with self.assertRaises(WorkflowExecutionError) as error:
            WritingWorkflow(StubLLM([assessment()]), self.store).run(
                WorkflowRequest.model_validate(
                    {**SOURCE_REQUEST, "mode": "assessment", "essay": "A draft."}
                )
            )
        self.assertEqual(error.exception.state.error.code, "invalid_output")

    def test_rubric_score_bounds_sum_and_not_scorable(self):
        """Verify rubric score bounds sum and not scorable."""
        body = (
            WritingWorkflow(MockLLM()).run(self.request).assessed_content.model_dump()
        )
        for name, score in (
            ("organization_purpose", 0),
            ("evidence_elaboration", 5),
            ("conventions", 3),
            ("conventions", "2"),
            ("conventions", True),
        ):
            invalid = copy.deepcopy(body)
            invalid["per_criterion"][name]["score"] = score
            with self.assertRaises(ValidationError):
                SourceAssessment.model_validate(invalid)
        with self.assertRaises(ValidationError):
            SourceAssessment.model_validate({**body, "total_score": 10})
        ns = {
            **body,
            "status": "not_scorable",
            "total_score": None,
            "per_criterion": None,
            "not_scorable_reason": "off_topic",
        }
        self.assertEqual(SourceAssessment.model_validate(ns).status, "not_scorable")
        with self.assertRaises(ValidationError):
            SourceAssessment.model_validate({**ns, "total_score": 0})
        with self.assertRaises(ValidationError):
            SourceAssessment.model_validate(
                {**body, "not_scorable_reason": "off_topic"}
            )

    def test_removed_prototype_grades_are_rejected_before_model(self):
        """Verify removed prototype grades are rejected before model."""
        llm = StubLLM([])
        with TestClient(api.create_app(WritingWorkflow(llm, self.store))) as client:
            for grade in ("elem_6", "mid_2", "high_2"):
                response = client.post(
                    "/run",
                    json={
                        **SOURCE_REQUEST,
                        "grade_for_student": grade,
                        "grade_for_assessor": grade,
                    },
                )
                self.assertEqual(response.status_code, 422)
        self.assertEqual(llm.calls, [])

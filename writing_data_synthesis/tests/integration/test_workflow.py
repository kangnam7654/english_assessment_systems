"""Offline checks for explicit state, model boundaries and the HTTP contract."""

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import chdir
from unittest.mock import patch

import writing_synthesis.app as api
from fastapi.testclient import TestClient
from writing_synthesis.schemas.request import WorkflowRequest
from writing_synthesis.schemas.run import Stage
from writing_synthesis.workflows.runner import WorkflowExecutionError, WritingWorkflow

from tests.fixtures import assessment


class StubLLM:
    """Exercise stub l l m behavior with controlled fixtures."""
    def __init__(self, responses):
        """Initialize the controlled test double and its recorded responses.

        Args:
            responses: Ordered model responses returned by the test double.
        """
        self.responses = iter(responses)
        self.calls = []

    def complete(self, messages):
        """Return a controlled model response and record the supplied messages.

        Args:
            messages: Ordered role/content messages sent to the chat completion endpoint.

        Returns:
            Completed assistant text; Mock clients produce deterministic synthetic JSON.
        """
        self.calls.append(messages)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return json.dumps(response)


class WorkflowTests(unittest.TestCase):
    """Exercise workflow tests behavior with controlled fixtures."""
    def test_synthesis_from_unrelated_directory_and_assessor_context(self):
        """Verify synthesis from unrelated directory and assessor context."""
        llm = StubLLM([{"essay_english": "I enjoy writing."}, assessment(3)])
        request = WorkflowRequest(user_prompt="Write about a hobby.", level="beginner")
        with tempfile.TemporaryDirectory() as directory, chdir(directory):
            result = WritingWorkflow(llm).run(request)
        self.assertEqual(result.essay, "I enjoy writing.")
        self.assertEqual(result.assessed_content.model_dump(), assessment(3))
        self.assertEqual(
            result.history,
            [
                Stage.PENDING,
                Stage.PREPARING,
                Stage.GENERATING,
                Stage.ASSESSING,
                Stage.COMPLETED,
            ],
        )
        self.assertEqual(request.mode, "synthesis")
        payload = json.loads(llm.calls[1][1]["content"])
        self.assertEqual(
            json.loads(payload["assignment"]),
            {"task": request.user_prompt, "genre": "narrative", "source_passages": []},
        )
        self.assertNotIn("Target level:", llm.calls[1][0]["content"])
        self.assertNotIn("level", payload)

    def test_assessment_skips_generation(self):
        """Verify assessment skips generation."""
        llm = StubLLM([assessment(2)])
        result = WritingWorkflow(llm).run(
            WorkflowRequest(
                mode="assessment", user_prompt="A hobby", essay="My own essay."
            )
        )
        self.assertEqual(result.essay, "My own essay.")
        self.assertEqual(len(llm.calls), 1)
        self.assertNotIn(Stage.GENERATING, result.history)
        self.assertEqual(
            json.loads(json.loads(llm.calls[0][1]["content"])["assignment"])["task"],
            "A hobby",
        )

    def test_templates_load_for_each_grade_and_level(self):
        """Verify templates load for each grade and level."""
        for grade in ("us_3", "us_6", "us_8"):
            for level in ("beginner", "intermediate", "advanced", "master"):
                with self.subTest(grade=grade, level=level):
                    llm = StubLLM(
                        [{"essay_english": "Example."}, assessment(3, grade=grade)]
                    )
                    result = WritingWorkflow(llm).run(
                        WorkflowRequest(
                            grade_for_student=grade,
                            grade_for_assessor=grade,
                            level=level,
                            user_prompt="A hobby.",
                        )
                    )
                    self.assertEqual(result.request.level, level)
                    self.assertEqual(result.stage, Stage.COMPLETED)

    def test_invalid_requests_fail_before_execution(self):
        """Verify invalid requests fail before execution."""
        for kwargs in (
            {"mode": "other"},
            {"user_prompt": " "},
            {"mode": "assessment", "user_prompt": "A hobby", "essay": " "},
            {"grade_for_student": "missing", "user_prompt": "Topic"},
            {"level": "missing", "user_prompt": "Topic"},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                WorkflowRequest(**kwargs)

    def test_generation_failure_prevents_assessment(self):
        """Verify generation failure prevents assessment."""
        for response in (
            {"essay_english": " "},
            {"essay_english": 42},
            [],
            RuntimeError("offline"),
        ):
            with self.subTest(response=response):
                llm = StubLLM([response])
                with self.assertRaises(WorkflowExecutionError) as raised:
                    WritingWorkflow(llm).run(WorkflowRequest(user_prompt="Topic"))
                state = raised.exception.state
                self.assertEqual(state.stage, Stage.FAILED)
                self.assertEqual(state.failed_stage, Stage.GENERATING)
                self.assertIsNone(state.assessed_content)
                self.assertEqual(len(llm.calls), 1)
                self.assertIsNotNone(raised.exception.__cause__)

    def test_assessment_failure_retains_generated_essay(self):
        """Verify assessment failure retains generated essay."""
        llm = StubLLM([{"essay_english": "Completed essay."}, {}])
        with self.assertRaises(WorkflowExecutionError) as raised:
            WritingWorkflow(llm).run(WorkflowRequest(user_prompt="Topic"))
        self.assertEqual(raised.exception.state.failed_stage, Stage.ASSESSING)
        self.assertEqual(raised.exception.state.essay, "Completed essay.")

    def test_preparation_failure_records_stage_without_calling_model(self):
        """Verify preparation failure records stage without calling model."""
        llm = StubLLM([])
        runner = WritingWorkflow(llm)
        with (
            patch(
                "writing_synthesis.prompts.preparation.PromptPreparation.build",
                side_effect=ValueError("bad resource"),
            ),
            self.assertRaises(WorkflowExecutionError) as raised,
        ):
            runner.run(WorkflowRequest(user_prompt="Topic"))
        self.assertEqual(raised.exception.state.failed_stage, Stage.PREPARING)
        self.assertEqual(llm.calls, [])

    def test_concurrent_runs_do_not_share_state(self):
        """Verify concurrent runs do not share state."""
        class EchoAssessment:
            """Exercise echo assessment behavior with controlled fixtures."""
            def complete(self, messages):
                """Return a controlled model response and record the supplied messages.

                Args:
                    messages: Ordered role/content messages sent to the chat completion endpoint.

                Returns:
                    Completed assistant text; Mock clients produce deterministic synthetic JSON.
                """
                result = assessment()
                result["summary_feedback_english"] = json.loads(messages[1]["content"])[
                    "essay"
                ]
                return json.dumps(result)

        runner = WritingWorkflow(EchoAssessment())
        requests = [
            WorkflowRequest(
                mode="assessment", user_prompt="A hobby", essay=f"Essay {i}"
            )
            for i in range(8)
        ]
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(runner.run, requests))
        for result, request in zip(results, requests):
            self.assertEqual(
                result.assessed_content.summary_feedback_english, request.essay
            )
            self.assertEqual(result.stage, Stage.COMPLETED)
        self.assertEqual(len({result.run_id for result in results}), len(results))
        with self.assertRaises(ValueError):
            results[0].advance(Stage.GENERATING)

    def test_http_run_contract_with_local_stub(self):
        """Verify http run contract with local stub."""
        llm = StubLLM([{"essay_english": "An API essay."}, assessment(4)])
        with (
            TestClient(api.create_app(WritingWorkflow(llm))) as client,
        ):
            response = client.post(
                "/run", json={"mode": "synthesis", "user_prompt": "A hobby."}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {
                k: v
                for k, v in response.json().items()
                if k not in {"run_id", "schema_version", "stage"}
            },
            {
                "execution_mode": "unknown",
                "grade": "us_6",
                "level": "intermediate",
                "essay": "An API essay.",
                "assessed_content": assessment(4),
            },
        )

    def test_http_assessment_and_input_validation(self):
        """Verify http assessment and input validation."""
        llm = StubLLM([assessment(2)])
        with (
            TestClient(api.create_app(WritingWorkflow(llm))) as client,
        ):
            for body in (
                {"mode": "assessment"},
                {"user_prompt": " "},
                {"mode": "unknown"},
            ):
                self.assertEqual(client.post("/run", json=body).status_code, 422)
            response = client.post(
                "/run",
                json={
                    "mode": "assessment",
                    "user_prompt": "A hobby",
                    "essay": "Original",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(llm.calls), 1)

    def test_http_model_failure_does_not_expose_exception(self):
        """Verify http model failure does not expose exception."""
        llm = StubLLM([RuntimeError("private backend detail")])
        with (
            TestClient(api.create_app(WritingWorkflow(llm))) as client,
            self.assertLogs("writing_synthesis.api.routes", level="ERROR"),
        ):
            response = client.post("/run", json={"user_prompt": "Topic"})
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("private backend detail", response.text)


if __name__ == "__main__":
    unittest.main()

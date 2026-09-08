"""Offline checks for graph/resource/API behavior after moving this module."""

from contextlib import chdir
import json
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

import app as api
from config import create_initial_state
from workflow_builder import build_workflow


class StubLLM:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return AIMessage(content=json.dumps(next(self.responses)))


class WorkflowTests(unittest.TestCase):
    def test_synthesis_and_rubric_loading_outside_module_directory(self):
        llm = StubLLM([{"essay_english": "I enjoy writing."}, {"overall_score": 3}])
        with tempfile.TemporaryDirectory() as directory, chdir(directory):
            graph, context = build_workflow(llm)
            result = graph.invoke(create_initial_state(user_prompt="Write about a hobby."), context=context)
        self.assertEqual(result["essay"], "I enjoy writing.")
        self.assertEqual(result["assessed_content"], {"overall_score": 3})
        self.assertEqual(len(llm.calls), 2)
        self.assertEqual(llm.calls[1][1].content, result["essay"])
        self.assertTrue(all(call[0].content for call in llm.calls))

    def test_assessment_preserves_input_without_generating_an_essay(self):
        llm = StubLLM([{"overall_score": 2}])
        graph, context = build_workflow(llm)
        result = graph.invoke(create_initial_state(mode="assessment", essay="My own essay."), context=context)
        self.assertEqual(result["essay"], "My own essay.")
        self.assertEqual(len(llm.calls), 1)
        self.assertEqual(llm.calls[0][1].content, "My own essay.")

    def test_templates_load_for_each_grade_and_level(self):
        for grade in ("elem_6", "mid_2", "high_2"):
            for level in ("beginner", "intermediate", "advanced", "master"):
                with self.subTest(grade=grade, level=level):
                    llm = StubLLM([{"essay_english": "Example."}, {"overall_score": 3}])
                    graph, context = build_workflow(llm)
                    result = graph.invoke(create_initial_state(grade_for_student=grade,
                        grade_for_assessor=grade, level=level, user_prompt="A hobby."), context=context)
                    self.assertEqual(result["level"], level)
                    self.assertEqual(len(llm.calls), 2)

    def test_http_run_contract_with_local_stub(self):
        llm = StubLLM([{"essay_english": "An API essay."}, {"overall_score": 4}])
        graph, context = build_workflow(llm)
        with patch.object(api, "graph", graph), patch.object(api, "context_state", context):
            with TestClient(api.app) as client:
                response = client.post("/run", json={"mode": "synthesis", "user_prompt": "A hobby."})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["essay"], "An API essay.")
        self.assertEqual(response.json()["assessed_content"], {"overall_score": 4})


if __name__ == "__main__":
    unittest.main()

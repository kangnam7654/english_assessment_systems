"""The UI receives the actual execution mode, without model endpoint metadata."""

import unittest

from fastapi.testclient import TestClient
from writing_synthesis.app import create_app
from writing_synthesis.llm.mock import MockLLM
from writing_synthesis.schemas.provenance import ModelSnapshot
from writing_synthesis.workflows.runner import WritingWorkflow


class RuntimeTests(unittest.TestCase):
    """Exercise runtime tests behavior with controlled fixtures."""
    def test_execution_mode_matches_injected_workflow(self):
        """Verify execution mode matches injected workflow."""
        for mode in ("mock", "live", "unknown"):
            workflow = WritingWorkflow(MockLLM())
            workflow.model = ModelSnapshot(
                adapter="test",
                execution_mode=mode,
                base_url="http://private-model.invalid",
            )
            with TestClient(create_app(workflow)) as client:
                response = client.get("/runtime")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"execution_mode": mode})

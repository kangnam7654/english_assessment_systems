"""App boundaries: independent resources, caller ownership, startup cleanup."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import writing_synthesis.app as api
from fastapi.testclient import TestClient
from writing_synthesis.llm.mock import MockLLM
from writing_synthesis.storage.sqlite import SQLiteRunStore
from writing_synthesis.workflows.runner import WritingWorkflow


class AppLifecycleTests(unittest.TestCase):
    """Exercise app lifecycle tests behavior with controlled fixtures."""
    def test_two_apps_keep_workflows_and_run_storage_separate(self):
        """Verify two apps keep workflows and run storage separate."""
        with tempfile.TemporaryDirectory() as directory:
            models = [MockLLM(), MockLLM()]
            for model in models:
                model.close = Mock()
            apps = [
                api.create_app(
                    WritingWorkflow(
                        model, SQLiteRunStore(Path(directory) / f"app-{index}.sqlite3")
                    )
                )
                for index, model in enumerate(models)
            ]
            with TestClient(apps[0]) as first, TestClient(apps[1]) as second:
                first_run = first.post("/run", json={"user_prompt": "First task"})
                second_run = second.post("/run", json={"user_prompt": "Second task"})
                self.assertEqual(first_run.status_code, 200)
                self.assertEqual(second_run.status_code, 200)
                first_id, second_id = (
                    first_run.json()["run_id"],
                    second_run.json()["run_id"],
                )
                self.assertNotEqual(first_id, second_id)
                self.assertEqual(first.get(f"/runs/{first_id}").status_code, 200)
                self.assertEqual(second.get(f"/runs/{second_id}").status_code, 200)
                self.assertEqual(first.get(f"/runs/{second_id}").status_code, 404)
                self.assertEqual(second.get(f"/runs/{first_id}").status_code, 404)
            for app, model in zip(apps, models):
                self.assertFalse(hasattr(app.state, "workflow"))
                model.close.assert_not_called()  # The caller owns injected resources.

    def test_factory_does_not_open_resources_until_startup(self):
        """Verify factory does not open resources until startup."""
        with (
            patch.object(api, "create_llm") as llm,
            patch.object(api, "create_store") as store,
        ):
            application = api.create_app()
            self.assertIn("/run", application.openapi()["paths"])
            llm.assert_not_called()
            store.assert_not_called()

    def test_startup_failure_closes_owned_model(self):
        """Verify startup failure closes owned model."""
        model = MockLLM()
        model.close = Mock()
        application = api.create_app()
        with (
            patch.object(api, "create_store"),
            patch.object(api, "create_llm", return_value=model),
            patch.object(
                api, "WritingWorkflow", side_effect=RuntimeError("bad resource")
            ),
            self.assertRaisesRegex(RuntimeError, "bad resource"),
            TestClient(application),
        ):
            pass
        model.close.assert_called_once_with()
        self.assertFalse(hasattr(application.state, "workflow"))

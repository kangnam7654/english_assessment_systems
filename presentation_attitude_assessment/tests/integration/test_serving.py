"""Regression checks for serving."""

import asyncio
import hashlib
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient

from presentation_attitude.serving.api import create_app
from presentation_attitude.serving.contracts import Conflict
from presentation_attitude.serving.files import LocalJobFiles
from presentation_attitude.serving.settings import Settings
from presentation_attitude.serving.store import JobStore
from presentation_attitude.serving.worker import JobWorker, run_worker, worker_lock


class ServingTests(unittest.TestCase):
    """Exercise serving tests behavior with controlled fixtures."""
    def setUp(self):
        """Create isolated fixtures and register cleanup for this test scope."""
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.settings = Settings(self.directory / "service")
        self.client = self.enterContext(TestClient(create_app(self.settings)))
        self.store = JobStore(self.settings.data_dir)
        self.files = LocalJobFiles(self.settings.data_dir)

    def upload(self, payload=b"video", **params):
        """Submit the supplied video bytes through the test client.

        Args:
            payload: Video bytes sent to the test upload endpoint.
            **params: Additional upload query parameters.

        Returns:
            TestClient response from the upload endpoint.
        """
        return self.client.post(
            "/jobs",
            files={"file": ("../../talk.mp4", payload, "video/mp4")},
            params=params,
        )

    def test_upload_claim_result_and_api_restart(self):
        """Verify upload claim result and api restart."""
        response = self.upload()
        self.assertEqual(response.status_code, 202)
        job = response.json()
        self.assertEqual(job["filename"], "talk.mp4")
        self.assertEqual(job["source_sha256"], hashlib.sha256(b"video").hexdigest())
        self.assertEqual(self.client.get(job["result_url"]).status_code, 409)
        self.assertEqual(
            self.client.post(f"{job['status_url']}/retry").status_code, 409
        )
        entered, release = threading.Event(), threading.Event()

        def analyze(source, output, mode):
            """Provide the controlled analyzer behavior for this worker scenario.

            Args:
                source: Source video path or caller-owned input stream, as required by this
                    operation.
                output: Destination directory or file for generated artifacts.
                mode: Requested execution mode.

            Returns:
                Controlled result used by this worker scenario.
            """
            self.assertEqual(source.read_bytes(), b"video")
            self.assertEqual(mode, "features")
            entered.set()
            release.wait(5)
            return {"features": {"frames": 5}, "assessment": None}

        worker = JobWorker(self.store, analyze, files=self.files)
        thread = threading.Thread(target=worker.run_once)
        thread.start()
        try:
            self.assertTrue(entered.wait(5))
            self.assertEqual(
                self.client.get(job["status_url"]).json()["status"], "running"
            )
            self.assertEqual(self.client.get("/health").status_code, 200)
        finally:
            release.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        with TestClient(create_app(self.settings)) as restarted:
            self.assertEqual(
                restarted.get(job["status_url"]).json()["status"], "succeeded"
            )
            self.assertIsNone(restarted.get(job["result_url"]).json()["assessment"])
        self.assertFalse(worker.run_once())

    def test_failure_retry_preserves_history_and_distinct_output(self):
        """Verify failure retry preserves history and distinct output."""
        job = self.upload().json()
        outputs = []

        def analyze(source, output, mode):
            """Provide the controlled analyzer behavior for this worker scenario.

            Args:
                source: Source video path or caller-owned input stream, as required by this
                    operation.
                output: Destination directory or file for generated artifacts.
                mode: Requested execution mode.

            Returns:
                Controlled result used by this worker scenario.
            """
            outputs.append(output)
            output.mkdir()
            if len(outputs) == 1:
                raise RuntimeError("private local path detail")
            return {"assessment": None}

        worker = JobWorker(self.store, analyze, files=self.files)
        with self.assertLogs("presentation_attitude.serving.worker", level="ERROR"):
            worker.run_once()
        status = self.client.get(job["status_url"]).json()
        self.assertEqual(status["status"], "failed")
        self.assertNotIn("private local path", json.dumps(status))
        self.assertEqual(self.client.get(job["result_url"]).status_code, 409)
        self.assertEqual(
            self.client.post(f"{job['status_url']}/retry").status_code, 202
        )
        self.assertEqual(
            self.client.post(f"{job['status_url']}/retry").status_code, 409
        )
        worker.run_once()
        status = self.client.get(job["status_url"]).json()
        self.assertEqual(
            [a["status"] for a in status["attempts"]], ["failed", "succeeded"]
        )
        self.assertNotEqual(*outputs)

    def test_atomic_claim_and_stale_completion_rejected(self):
        """Verify atomic claim and stale completion rejected."""
        job = self.upload().json()
        other = JobStore(self.settings.data_dir)
        results = []
        threads = [
            threading.Thread(target=lambda store=store: results.append(store.claim()))
            for store in (self.store, other)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sum(r is not None for r in results), 1)
        with worker_lock(self.settings.data_dir):
            self.assertEqual(self.store.recover_interrupted(), 1)
        self.store.retry(job["id"])
        second = self.store.claim()
        with self.assertRaises(Conflict):
            self.store.finish(job["id"], 1, result={})
        self.assertEqual(second["attempt"], 2)

    def test_reject_bad_uploads_and_unknown_jobs(self):
        """Verify reject bad uploads and unknown jobs."""
        self.assertEqual(self.upload(b"").status_code, 400)
        self.assertEqual(
            self.client.post("/jobs", files={"file": ("a.txt", b"x")}).status_code, 415
        )
        self.assertEqual(self.upload(mode="unknown").status_code, 422)
        self.assertEqual(self.client.get("/jobs/not-a-uuid").status_code, 422)
        self.assertEqual(self.client.get("/jobs/" + "0" * 32).status_code, 404)
        self.assertEqual(list((self.settings.data_dir / "jobs").iterdir()), [])
        with TestClient(
            create_app(Settings(self.directory / "limited", max_upload_bytes=3))
        ) as client:
            self.assertEqual(
                client.post("/jobs", files={"file": ("a.mp4", b"1234")}).status_code,
                413,
            )
            self.assertEqual(
                client.post("/jobs", content=b"x" * 70000).status_code, 413
            )
        self.assertEqual(list((self.directory / "limited/jobs").iterdir()), [])

    def test_streamed_upload_limit_without_content_length(self):
        """Verify streamed upload limit without content length."""
        async def request():
            """Build or submit the request used by this test scenario.

            Returns:
                Request payload or test response used by this scenario.
            """
            app = create_app(Settings(self.directory / "streamed", max_upload_bytes=3))
            async with app.router.lifespan_context(app):
                chunks = iter(
                    [
                        b'--b\r\nContent-Disposition: form-data; name="file"; filename="x.mp4"\r\n\r\n',
                        b"x" * 70000,
                        b"\r\n--b--\r\n",
                    ]
                )
                sent = []

                async def receive():
                    """Supply the next ASGI message in the simulated upload.

                    Returns:
                        Next simulated ASGI request message.
                    """
                    return {
                        "type": "http.request",
                        "body": next(chunks),
                        "more_body": True,
                    }

                async def send(message):
                    """Capture an outgoing ASGI message for response assertions.

                    Args:
                        message: ASGI message to forward.
                    """
                    sent.append(message)

                await app(
                    {
                        "type": "http",
                        "asgi": {"version": "3.0"},
                        "http_version": "1.1",
                        "method": "POST",
                        "scheme": "http",
                        "path": "/jobs",
                        "raw_path": b"/jobs",
                        "query_string": b"",
                        "headers": [
                            (b"content-type", b"multipart/form-data; boundary=b")
                        ],
                        "client": ("127.0.0.1", 1),
                        "server": ("127.0.0.1", 2),
                    },
                    receive,
                    send,
                )
                return next(
                    m["status"] for m in sent if m["type"] == "http.response.start"
                )

        self.assertEqual(asyncio.run(request()), 413)

    def test_repository_failure_removes_staged_upload(self):
        """Verify repository failure removes staged upload."""
        self.client.app.state.store.create = Mock(
            side_effect=RuntimeError("Repository unavailable")
        )
        with self.assertRaisesRegex(RuntimeError, "Repository unavailable"):
            self.upload()
        self.assertEqual(list(self.files.directory.iterdir()), [])
        self.assertIsNone(self.store.claim())

    def test_worker_factory_is_loaded_once_for_multiple_jobs(self):
        """Verify worker factory is loaded once for multiple jobs."""
        self.upload()
        self.upload()
        stop, calls, loads = threading.Event(), [], []

        def factory():
            """Construct the test dependency and record the expected lifecycle behavior.

            Returns:
                Injected test dependency for the worker or repository.
            """
            loads.append(True)

            def analyze(*args):
                """Provide the controlled analyzer behavior for this worker scenario.

                Args:
                    *args: Unused positional inputs accepted by the test analyzer.

                Returns:
                    Controlled result used by this worker scenario.
                """
                calls.append(True)
                if len(calls) == 2:
                    stop.set()
                return {"assessment": None}

            return analyze

        run_worker(self.settings, factory, stop)
        self.assertEqual(len(loads), 1)
        self.assertEqual(len(calls), 2)

    def test_killed_worker_releases_lock_and_restart_recovers(self):
        """Verify killed worker releases lock and restart recovers."""
        job = self.upload().json()
        code = """
import sys, time
from pathlib import Path
from presentation_attitude.serving.store import JobStore
from presentation_attitude.serving.worker import worker_lock
directory = Path(sys.argv[1])
with worker_lock(directory):
    JobStore(directory).claim()
    print("claimed", flush=True)
    time.sleep(30)
"""
        process = subprocess.Popen(
            [sys.executable, "-c", code, str(self.settings.data_dir)],
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertEqual(process.stdout.readline().strip(), "claimed")
            with self.assertRaisesRegex(RuntimeError, "Another worker"):
                with worker_lock(self.settings.data_dir):
                    pass
            self.assertEqual(self.store.get(job["id"])["status"], "running")
        finally:
            process.kill()
            process.wait(timeout=5)
            process.stdout.close()
        run_worker(
            self.settings, lambda: lambda *args: {}, threading.Event(), once=True
        )
        recovered = self.store.get(job["id"])
        self.assertEqual(recovered["status"], "failed")
        self.assertEqual(
            recovered["attempts"][0]["error"]["code"], "worker_interrupted"
        )

    def test_tampered_upload_never_reaches_analyzer(self):
        """Verify tampered upload never reaches analyzer."""
        job = self.upload().json()
        (self.files.job_dir(job["id"]) / "source.video").write_bytes(b"different")
        analyzer = Mock()
        with self.assertLogs("presentation_attitude.serving.worker", level="ERROR"):
            JobWorker(self.store, analyzer, files=self.files).run_once()
        analyzer.assert_not_called()
        self.assertEqual(self.store.get(job["id"])["status"], "failed")

    def test_api_import_does_not_load_ml_runtimes(self):
        """Verify api import does not load ml runtimes."""
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from presentation_attitude.serving.api import create_app; import sys; assert 'torch' not in sys.modules; assert 'mediapipe' not in sys.modules",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_optional_ui_mount_preserves_api_and_does_not_expose_job_files(self):
        """Verify optional ui mount preserves api and does not expose job files."""
        ui = self.directory / "ui-dist"
        ui.mkdir()
        (ui / "index.html").write_text("<h1>Presentation Attitude</h1>")
        (ui / "app.js").write_text("window.uiReady = true;")
        with TestClient(create_app(self.settings, ui_dir=ui)) as client:
            self.assertEqual(client.get("/").url.path, "/ui/")
            self.assertIn("Presentation Attitude", client.get("/ui/").text)
            self.assertIn("uiReady", client.get("/ui/app.js").text)
            self.assertEqual(client.get("/health").json()["queue"], "sqlite")
            self.assertEqual(client.get("/ui/jobs.sqlite3").status_code, 404)
            self.assertEqual(client.get("/ui/%2e%2e/jobs.sqlite3").status_code, 404)
            response = client.post("/jobs", files={"file": ("a.mp4", b"video")})
            self.assertEqual(response.status_code, 202)
        with self.assertRaises(FileNotFoundError):
            create_app(self.settings, ui_dir=self.directory / "missing")

    def test_injected_repository_and_separate_files_support_retry_and_restart(self):
        """Verify injected repository and separate files support retry and restart."""
        settings = Settings(self.directory / "injected-runtime")
        files = LocalJobFiles(self.directory / "separate-artifacts")
        database_dir = self.directory / "separate-database"

        def factory(_):
            """Construct the test dependency and record the expected lifecycle behavior.

            Args:
                _: Unused factory input.

            Returns:
                Injected test dependency for the worker or repository.
            """
            repository = JobStore(database_dir)
            # Expose only the contract: no SQL connection or filesystem methods.
            return SimpleNamespace(
                **{
                    name: getattr(repository, name)
                    for name in (
                        "health",
                        "create",
                        "get",
                        "claim",
                        "finish",
                        "retry",
                        "recover_interrupted",
                    )
                }
            )

        def analyze(source, output, mode):
            """Provide the controlled analyzer behavior for this worker scenario.

            Args:
                source: Source video path or caller-owned input stream, as required by this
                    operation.
                output: Destination directory or file for generated artifacts.
                mode: Requested execution mode.

            Returns:
                Controlled result used by this worker scenario.
            """
            self.assertEqual(source.parent.parent, files.directory)
            self.assertEqual(source.read_bytes(), b"video")
            output.mkdir()
            if output.name == "attempt-1":
                raise ValueError("retry scenario")
            return {"assessment": None, "mode": mode}

        with TestClient(
            create_app(settings, store_factory=factory, files=files)
        ) as client:
            self.assertEqual(client.get("/health").json()["queue"], "sqlite")
            response = client.post("/jobs", files={"file": ("talk.mp4", b"video")})
            self.assertEqual(response.status_code, 202)
            job = response.json()
            with self.assertLogs("presentation_attitude.serving.worker", level="ERROR"):
                run_worker(
                    settings,
                    lambda: analyze,
                    threading.Event(),
                    once=True,
                    store_factory=factory,
                    files=files,
                )
            self.assertEqual(client.post(job["status_url"] + "/retry").status_code, 202)
            run_worker(
                settings,
                lambda: analyze,
                threading.Event(),
                once=True,
                store_factory=factory,
                files=files,
            )

        with TestClient(
            create_app(settings, store_factory=factory, files=files)
        ) as client:
            self.assertEqual(client.get(job["result_url"]).json()["mode"], "features")
            self.assertEqual(
                [a["status"] for a in client.get(job["status_url"]).json()["attempts"]],
                ["failed", "succeeded"],
            )
        self.assertTrue((database_dir / "jobs.sqlite3").exists())
        self.assertFalse((database_dir / "jobs").exists())
        self.assertFalse((settings.data_dir / "jobs.sqlite3").exists())

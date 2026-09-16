"""Exercise actual SDK serialization against an offline HTTP transport."""

import json
import os
import unittest
from unittest.mock import patch

import httpx2
import writing_synthesis.app as api
from fastapi.testclient import TestClient
from openai import APIStatusError, APITimeoutError
from writing_synthesis.llm.client import CompletionError, OpenAICompatibleLLM
from writing_synthesis.llm.settings import LLMSettings
from writing_synthesis.schemas.request import WorkflowRequest
from writing_synthesis.workflows.runner import WritingWorkflow

from tests.fixtures import assessment

DEFAULT_ASSESSMENT = json.dumps(assessment(3))


def completion(content=DEFAULT_ASSESSMENT, *, finish_reason="stop", **message):
    """Wrap assistant text in an OpenAI-compatible completion response fixture.

    Args:
        content: Assistant text to include in the fake completion.
        finish_reason: Completion status to expose in the fake provider response.
        **message: ASGI message to forward.

    Returns:
        OpenAI-compatible completion response dictionary.
    """
    return {
        "id": "test-completion",
        "object": "chat.completion",
        "created": 0,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish_reason,
                "message": {"role": "assistant", "content": content, **message},
            }
        ],
    }


class ClientTests(unittest.TestCase):
    """Exercise client tests behavior with controlled fixtures."""
    def make_client(self, handler, **settings):
        """Create a client backed by the injected mock HTTP handler.

        Args:
            handler: HTTP request handler for the mock transport.
            **settings: Validated configuration for this component.

        Returns:
            Model client configured with the mock HTTP transport.
        """
        client = OpenAICompatibleLLM(
            LLMSettings(**settings),
            http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
        )
        self.addCleanup(client.close)
        return client

    def test_workflow_uses_chat_completion_wire_format(self):
        """Verify workflow uses chat completion wire format."""
        requests = []

        def handle(request):
            """Return the scenario-specific fake HTTP response and inspect the request.

            Args:
                request: Validated writing request or HTTP request supplying app-scoped
                    resources.

            Returns:
                Mock HTTP response for the supplied request.
            """
            requests.append(request)
            body = (
                '{"essay_english": "An essay."}'
                if len(requests) == 1
                else json.dumps(assessment(3))
            )
            return httpx2.Response(200, json=completion(body))

        llm = self.make_client(
            handle,
            base_url="https://example.test/custom/v1",
            model="test-model",
            api_key="test-key",
        )
        result = WritingWorkflow(llm).run(WorkflowRequest(user_prompt="A hobby"))
        self.assertEqual(result.essay, "An essay.")
        self.assertEqual(len(requests), 2)
        for request in requests:
            self.assertEqual(request.method, "POST")
            self.assertEqual(
                str(request.url), "https://example.test/custom/v1/chat/completions"
            )
            self.assertEqual(request.headers["authorization"], "Bearer test-key")
            body = json.loads(request.content)
            self.assertEqual(set(body), {"model", "messages"})
            self.assertEqual(body["model"], "test-model")
            self.assertEqual([m["role"] for m in body["messages"]], ["system", "user"])
        assessor_input = json.loads(
            json.loads(requests[1].content)["messages"][1]["content"]
        )
        self.assertEqual(
            json.loads(assessor_input["assignment"]),
            {"task": "A hobby", "genre": "narrative", "source_passages": []},
        )

    def test_optional_provider_parameters_are_explicit(self):
        """Verify optional provider parameters are explicit."""
        bodies = []

        def handle(request):
            """Return the scenario-specific fake HTTP response and inspect the request.

            Args:
                request: Validated writing request or HTTP request supplying app-scoped
                    resources.

            Returns:
                Mock HTTP response for the supplied request.
            """
            bodies.append(json.loads(request.content))
            return httpx2.Response(200, json=completion())

        llm = self.make_client(handle, temperature=0, json_mode=True)
        llm.complete([{"role": "user", "content": "Return JSON"}])
        self.assertEqual(bodies[0]["temperature"], 0)
        self.assertEqual(bodies[0]["response_format"], {"type": "json_object"})

    def test_rejects_incomplete_refused_and_empty_responses(self):
        """Verify rejects incomplete refused and empty responses."""
        for body in [
            completion(finish_reason="length"),
            completion(finish_reason="content_filter"),
            completion(refusal="Refused"),
            completion(content=None),
            completion(content=" "),
            completion(finish_reason="tool_calls"),
            {**completion(), "choices": []},
        ]:
            with self.subTest(body=body):
                llm = self.make_client(
                    lambda request, body=body: httpx2.Response(200, json=body)
                )
                with self.assertRaises(CompletionError):
                    llm.complete([{"role": "user", "content": "Return JSON"}])

    def test_http_errors_are_not_silently_retried_or_rerouted(self):
        """Verify http errors are not silently retried or rerouted."""
        for status in [401, 429, 500]:
            calls = []

            def handle(request, calls=calls, status=status):
                """Return the scenario-specific fake HTTP response and inspect the request.

                Args:
                    request: Validated writing request or HTTP request supplying app-scoped
                        resources.
                    calls: Mutable collection used to record provider invocations.
                    status: HTTP status returned by the mock transport.

                Returns:
                    Mock HTTP response for the supplied request.
                """
                calls.append(request)
                return httpx2.Response(
                    status, json={"error": {"message": "test failure"}}
                )

            with self.subTest(status=status):
                llm = self.make_client(handle)
                with self.assertRaises(APIStatusError):
                    llm.complete([{"role": "user", "content": "Return JSON"}])
                self.assertEqual(len(calls), 1)

    def test_timeout_is_configured_and_not_retried(self):
        """Verify timeout is configured and not retried."""
        calls = []

        def handle(request):
            """Return the scenario-specific fake HTTP response and inspect the request.

            Args:
                request: Validated writing request or HTTP request supplying app-scoped
                    resources.
            """
            calls.append(request)
            self.assertEqual(request.extensions["timeout"]["read"], 7)
            raise httpx2.ReadTimeout("offline test", request=request)

        llm = self.make_client(handle, timeout_seconds=7)
        with self.assertRaises(APITimeoutError):
            llm.complete([{"role": "user", "content": "Return JSON"}])
        self.assertEqual(len(calls), 1)

    def test_environment_configuration_does_not_reuse_ambient_openai_key(self):
        """Verify environment configuration does not reuse ambient openai key."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "unrelated-secret"}, clear=True):
            settings = LLMSettings.from_env()
            self.assertEqual(settings.api_key, "local")
            self.assertEqual(settings.base_url, "http://localhost:11434/v1")
        env = {
            "WDS_LLM_BASE_URL": "https://example.test/v1",
            "WDS_LLM_MODEL": "remote-model",
            "WDS_LLM_API_KEY": "specific-secret",
            "WDS_LLM_JSON_MODE": "true",
            "WDS_LLM_TEMPERATURE": "0",
            "WDS_LLM_TIMEOUT_SECONDS": "45",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = LLMSettings.from_env()
        self.assertEqual(settings.model, "remote-model")
        self.assertEqual(settings.temperature, 0)
        self.assertTrue(settings.json_mode)
        self.assertNotIn("specific-secret", repr(settings))

    def test_invalid_settings_fail_without_http(self):
        """Verify invalid settings fail without http."""
        for env in [
            {"WDS_LLM_BASE_URL": "https://example.test/v1"},
            {"WDS_LLM_TIMEOUT_SECONDS": "nan"},
            {"WDS_LLM_TEMPERATURE": "3"},
            {"WDS_LLM_JSON_MODE": "maybe"},
            {"WDS_LLM_MODEL": " "},
        ]:
            with (
                self.subTest(env=env),
                patch.dict(os.environ, env, clear=True),
                self.assertRaises(ValueError),
            ):
                LLMSettings.from_env()

    def test_api_owns_and_closes_model_client_per_lifespan(self):
        """Verify api owns and closes model client per lifespan."""
        clients = []

        def make():
            """Construct the scenario's model client fixture.

            Returns:
                Model client instance tracked by the lifecycle test.
            """
            client = self.make_client(
                lambda request: httpx2.Response(200, json=completion())
            )
            clients.append(client)
            return client

        with patch.object(api, "create_llm", side_effect=make):
            for _ in range(2):
                with TestClient(api.app) as client:
                    self.assertFalse(clients[-1].client.is_closed())
                    self.assertEqual(
                        client.post(
                            "/run",
                            json={
                                "mode": "assessment",
                                "user_prompt": "A hobby",
                                "essay": "Essay",
                            },
                        ).status_code,
                        200,
                    )
                self.assertTrue(clients[-1].client.is_closed())
        self.assertIsNot(clients[0], clients[1])

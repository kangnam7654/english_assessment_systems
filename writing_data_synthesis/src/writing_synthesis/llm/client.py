"""OpenAI SDK adapter for non-streaming Chat Completions endpoints."""

from typing import cast

import httpx2
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from writing_synthesis.llm.settings import LLMSettings
from writing_synthesis.llm.types import ChatMessage
from writing_synthesis.schemas.provenance import ModelSnapshot


class CompletionError(ValueError):
    """The server returned no complete, usable assistant text."""


class OpenAICompatibleLLM:
    """Adapt the OpenAI SDK chat interface to the project's model-client contract."""
    def __init__(
        self, settings: LLMSettings, *, http_client: httpx2.Client | None = None
    ):
        """Configure an SDK client with the supplied endpoint, credentials, and timeout.

        Args:
            settings: Validated configuration for this component.
            http_client: Optional caller-supplied HTTP transport for the OpenAI SDK.
        """
        self.settings = settings
        self.client = OpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key,
            timeout=settings.timeout_seconds,
            max_retries=0,
            http_client=http_client,
        )

    def complete(self, messages: list[ChatMessage]) -> str:
        """Request one nonstreaming chat completion and reject incomplete assistant output.

        Args:
            messages: Ordered role/content messages sent to the chat completion endpoint.

        Returns:
            Completed assistant text; Mock clients produce deterministic synthetic JSON.

        Raises:
            CompletionError: Completion has no choices; Completion did not finish normally;
                Expected assistant text, not refusal or tool calls; Completion contains no
                assistant text.
        """
        options = {}
        if self.settings.temperature is not None:
            options["temperature"] = self.settings.temperature
        if self.settings.json_mode:
            options["response_format"] = {"type": "json_object"}
        response = self.client.chat.completions.create(
            model=self.settings.model,
            messages=cast(list[ChatCompletionMessageParam], messages),
            **options,
        )
        if not response.choices:
            raise CompletionError("Completion has no choices.")
        choice = response.choices[0]
        if choice.finish_reason != "stop":
            raise CompletionError("Completion did not finish normally.")
        message = choice.message
        if message is None or message.refusal or message.tool_calls:
            raise CompletionError("Expected assistant text, not refusal or tool calls.")
        if not isinstance(message.content, str) or not message.content.strip():
            raise CompletionError("Completion contains no assistant text.")
        return message.content

    def describe(self) -> ModelSnapshot:
        """Explicit allowlist of reproducibility fields; never include api_key.

        Returns:
            Allowlisted model identity and execution settings without credentials.
        """
        return ModelSnapshot(
            adapter=type(self).__name__,
            execution_mode="live",
            model=self.settings.model,
            base_url=self.settings.base_url,
            temperature=self.settings.temperature,
            json_mode=self.settings.json_mode,
            timeout_seconds=self.settings.timeout_seconds,
        )

    def close(self) -> None:
        """Release the SDK's HTTP connection pool."""
        self.client.close()

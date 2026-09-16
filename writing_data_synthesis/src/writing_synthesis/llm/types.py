"""The text-only subset of the Chat Completions message format."""

from typing import Literal, Protocol, TypedDict


class ChatMessage(TypedDict):
    """Represent a text-only chat message with its role and content."""
    role: Literal["system", "user", "assistant"]
    content: str


class LanguageModel(Protocol):
    """Define the text-completion interface shared by real and Mock providers."""
    def complete(self, messages: list[ChatMessage]) -> str:
        """Return a completed assistant text or raise on an unusable response.

        Args:
            messages: Ordered role/content messages sent to the chat completion endpoint.

        Returns:
            Completed assistant text; Mock clients produce deterministic synthetic JSON.
        """
        ...

"""Endpoint configuration isolated from other applications' OpenAI credentials."""

import math
import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class LLMSettings:
    """Hold validated OpenAI-compatible model, endpoint, and request settings."""
    base_url: str = "http://localhost:11434/v1"
    model: str = "gpt-oss:20b"
    api_key: str = field(default="local", repr=False)
    timeout_seconds: float = 120
    temperature: float | None = None
    json_mode: bool = False

    def __post_init__(self) -> None:
        """Validate model configuration, URL scheme, and positive request limits.

        Raises:
            ValueError: LLM base_url must be an HTTP(S) API root without credentials, query
                or fragment; LLM model and api_key must be nonblank; LLM timeout must be
                positive and finite; LLM temperature must be between 0 and 2.
        """
        url = urlsplit(self.base_url)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError(
                "LLM base_url must be an HTTP(S) API root without credentials, query or fragment."
            )
        if not self.model.strip() or not self.api_key.strip():
            raise ValueError("LLM model and api_key must be nonblank.")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("LLM timeout must be positive and finite.")
        if self.temperature is not None and (
            not math.isfinite(self.temperature) or not 0 <= self.temperature <= 2
        ):
            raise ValueError("LLM temperature must be between 0 and 2.")

    @classmethod
    def from_env(cls) -> "LLMSettings":
        """Load the model connection configuration from WDS_LLM environment variables.

        Returns:
            Validated settings populated from environment variables and defaults.

        Raises:
            ValueError: Set WDS_LLM_API_KEY for a remote endpoint (use a placeholder for an
                unauthenticated server); WDS_LLM_JSON_MODE must be true or false.
        """
        base_url = os.environ.get("WDS_LLM_BASE_URL", "http://localhost:11434/v1")
        api_key = os.environ.get("WDS_LLM_API_KEY")
        if api_key is None:
            if urlsplit(base_url).hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError(
                    "Set WDS_LLM_API_KEY for a remote endpoint (use a placeholder for an unauthenticated server)."
                )
            api_key = "local"
        temperature = os.environ.get("WDS_LLM_TEMPERATURE", "").strip()
        json_mode = os.environ.get("WDS_LLM_JSON_MODE", "false").lower()
        if json_mode not in {"true", "false"}:
            raise ValueError("WDS_LLM_JSON_MODE must be true or false.")
        return cls(
            base_url=base_url,
            model=os.environ.get("WDS_LLM_MODEL", "gpt-oss:20b"),
            api_key=api_key,
            timeout_seconds=float(os.environ.get("WDS_LLM_TIMEOUT_SECONDS", "120")),
            temperature=float(temperature) if temperature else None,
            json_mode=json_mode == "true",
        )

"""Build a provider-independent workflow from environment configuration."""

import os
from pathlib import Path

from writing_synthesis.llm.client import OpenAICompatibleLLM
from writing_synthesis.llm.mock import MockLLM
from writing_synthesis.llm.settings import LLMSettings
from writing_synthesis.paths import REPO_DIR
from writing_synthesis.storage.sqlite import SQLiteRunStore


def create_llm() -> OpenAICompatibleLLM | MockLLM:
    """Select a Mock or OpenAI-compatible client from WDS_LLM_MODE.

    Returns:
        Configured Mock or OpenAI-compatible model client.

    Raises:
        ValueError: WDS_LLM_MODE must be openai or mock.
    """
    mode = os.getenv("WDS_LLM_MODE", "openai")
    if mode == "mock":
        return MockLLM()
    if mode != "openai":
        raise ValueError("WDS_LLM_MODE must be openai or mock.")
    return OpenAICompatibleLLM(LLMSettings.from_env())


def create_store() -> SQLiteRunStore:
    """Create SQLite workflow storage beneath the configured WDS data directory.

    Returns:
        SQLite repository for persisted writing runs.
    """
    default = REPO_DIR / ".local-data/writing-data-synthesis"
    directory = Path(os.getenv("WDS_DATA_DIR", str(default))).expanduser()
    return SQLiteRunStore(directory / "runs.sqlite3")

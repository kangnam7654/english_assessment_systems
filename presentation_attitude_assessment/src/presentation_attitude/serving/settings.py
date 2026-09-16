"""Shared local serving configuration; no ML imports."""

import os
from dataclasses import dataclass
from pathlib import Path

from presentation_attitude.paths import workspace_root


@dataclass(frozen=True)
class Settings:
    """Configure local storage and positive upload/frame limits."""
    data_dir: Path
    max_upload_bytes: int = 256 * 1024 * 1024
    max_frames: int = 10000

    def __post_init__(self):
        """Resolve the storage directory and reject nonpositive resource limits.

        Raises:
            ValueError: Upload and frame limits must be positive.
        """
        object.__setattr__(self, "data_dir", Path(self.data_dir).resolve())
        if self.max_upload_bytes < 1 or self.max_frames < 1:
            raise ValueError("Upload and frame limits must be positive")

    @classmethod
    def from_env(cls):
        """Read PAA storage and resource limits from environment variables.

        Returns:
            Validated settings populated from environment variables and defaults.
        """
        directory = os.environ.get("PAA_DATA_DIR")
        return cls(
            Path(directory) if directory else workspace_root() / ".local-data/serving",
            max_upload_bytes=int(
                os.environ.get("PAA_MAX_UPLOAD_BYTES", 256 * 1024 * 1024)
            ),
            max_frames=int(os.environ.get("PAA_MAX_FRAMES", 10000)),
        )

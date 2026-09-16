"""Shared primitives for supported K–12 writing requests."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

USGrade = Literal[
    "us_K",
    "us_1",
    "us_2",
    "us_3",
    "us_4",
    "us_5",
    "us_6",
    "us_7",
    "us_8",
    "us_9",
    "us_10",
    "us_11",
    "us_12",
]
Grade = USGrade
Level = Literal["beginner", "intermediate", "advanced", "master"]
Genre = Literal["opinion", "argumentative", "informative", "narrative"]
Mode = Literal["synthesis", "assessment"]
Text = Annotated[str, StringConstraints(strict=True, min_length=1, pattern=r"\S")]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp for persisted records.

    Returns:
        Timezone-aware datetime in UTC.
    """
    return datetime.now(UTC)


class Record(BaseModel):
    """Reject unknown fields and prevent accidental in-place record changes."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

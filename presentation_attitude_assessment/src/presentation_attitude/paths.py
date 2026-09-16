"""Locate monorepo resources for command-line workflows."""

from pathlib import Path


def workspace_root():
    # Editable installs also work when invoked outside the repository.
    """Find the enclosing portfolio checkout used to locate project resources.

    Returns:
        Absolute path of the enclosing portfolio repository.

    Raises:
        FileNotFoundError: Run this command from the english_assessment_systems checkout
            to locate configs and local media.
    """
    for start in (Path.cwd(), Path(__file__).resolve().parent):
        for candidate in (start, *start.parents):
            if (
                candidate / "presentation_attitude_assessment/configs/models.json"
            ).is_file() and (candidate / "pyproject.toml").is_file():
                return candidate
    raise FileNotFoundError(
        "Run this command from the english_assessment_systems checkout to locate configs and local media."
    )

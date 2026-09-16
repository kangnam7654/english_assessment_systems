"""Resource locations for the editable portfolio checkout.

WDS_PROJECT_DIR can point to the project resources when code is installed elsewhere.
"""
import os
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("WDS_PROJECT_DIR", Path(__file__).resolve().parents[2])).resolve()
REPO_DIR = PROJECT_DIR.parent

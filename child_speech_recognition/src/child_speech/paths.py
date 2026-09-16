"""Resource locations for the editable portfolio checkout."""
import os
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("ASR_PROJECT_DIR", Path(__file__).resolve().parents[2])).resolve()
REPO_DIR = PROJECT_DIR.parent

from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = BACKEND_DIR / "data" / "workbench.sqlite"
DEFAULT_METRIC_CATALOG_PATH = BACKEND_DIR / "fixtures" / "metric_definitions.json"


def get_database_path() -> Path:
    configured_path = os.environ.get("AGENT_VALIDATOR_DB_PATH")
    return Path(configured_path).expanduser() if configured_path else DEFAULT_DATABASE_PATH

from __future__ import annotations

import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from backend.app.services.orchestrators.factor_view_orchestrator import main


if __name__ == "__main__":
    main()

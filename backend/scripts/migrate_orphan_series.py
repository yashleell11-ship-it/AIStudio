"""Migrate orphan series created by incorrect imports.

Run from the backend directory:

    venv\\Scripts\\python.exe scripts\\migrate_orphan_series.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from cli import migrate_orphan_series


if __name__ == "__main__":
    removed = migrate_orphan_series()
    print(f"Removed {removed} orphan series.")

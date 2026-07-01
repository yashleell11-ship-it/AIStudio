"""Ensure the backend root is on sys.path for all entry points."""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent


def setup_path() -> Path:
    root = str(_BACKEND_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    return _BACKEND_ROOT

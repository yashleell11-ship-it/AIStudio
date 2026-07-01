"""AIStudio backend package.

When imported as ``backend`` (e.g. ``python -m backend.main`` from the repo
root), ensure the backend application root is on ``sys.path`` so flat imports
like ``database`` and ``services`` resolve correctly.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent
_ROOT = str(_BACKEND_ROOT)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

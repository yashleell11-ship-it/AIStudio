"""Shared UTC timestamp helper.

``datetime.utcnow()`` is deprecated (Python 3.12+) in favour of timezone-aware
``datetime.now(timezone.utc)``. Every timestamp column in this project is a
naive SQLite ``DATETIME`` representing UTC (no ``timezone=True``), so we
compute the correct instant via the non-deprecated API and then drop the
tzinfo before it touches the ORM -- this keeps every existing comparison
(naive vs. naive) working exactly as before while silencing the deprecation.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current UTC time as a naive ``datetime`` (matches existing DB columns)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

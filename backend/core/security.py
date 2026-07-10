"""Lightweight admin guard for destructive / admin-only endpoints.

P0 stop-gap until full user authentication (P1). Backup export/import and
library folder-import are admin operations that must never be open to anonymous
callers (a backup import replaces the whole database on next restart; a folder
import can mount any host directory). The guard is driven by the
``MM_ADMIN_TOKEN`` environment variable:

* if ``MM_ADMIN_TOKEN`` is unset/empty, the guarded endpoints are **disabled**
  (fail closed) — a deployment must explicitly opt in by setting a token;
* if it is set, callers must present a matching ``X-Admin-Token`` header.

Deliberately minimal; it will be replaced by real role-based auth when user
accounts land in P1.
"""

from __future__ import annotations

import os
import secrets

from fastapi import Header

from core.errors import AppError

ADMIN_TOKEN_ENV = "MM_ADMIN_TOKEN"


def require_admin(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> None:
    """FastAPI dependency authorizing admin-only endpoints (fail closed)."""
    expected = os.getenv(ADMIN_TOKEN_ENV, "")
    if not expected:
        raise AppError(
            "Admin operations are disabled. Set the MM_ADMIN_TOKEN environment "
            "variable to enable backup and import endpoints.",
            code="admin_disabled",
            status_code=503,
        )
    if not x_admin_token or not secrets.compare_digest(x_admin_token, expected):
        raise AppError(
            "A valid X-Admin-Token header is required for this operation.",
            code="admin_unauthorized",
            status_code=401,
        )

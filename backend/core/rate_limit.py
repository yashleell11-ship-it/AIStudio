"""Inbound rate limiting (slowapi).

A single process-wide limiter, keyed by the real client IP as reported by the
outermost proxy (the app runs behind Caddy/Cloudflare, so the socket peer is
the proxy — see :func:`client_ip` for why that is *not* X-Forwarded-For).
Applied selectively to the expensive/abusable endpoints — auth
(login/register), the admin backup restore-upload, and source proxying
(browse/search/cover/page-image) — via the per-bucket limit callables below.

The limit *values* are read from Settings on every request, so they stay
env-configurable (MM_RATE_LIMIT_AUTH / _IMPORT / _SOURCES) without touching
code. Set MM_RATE_LIMIT_ENABLED=false to turn limiting off globally.

Storage is in-memory: limits are enforced per worker process. That is sufficient
as a brute-force/abuse backstop; it is not a precise cluster-wide quota.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from core.config import get_settings


def client_ip(request: Request) -> str:
    """Rate-limit key: the originating client IP.

    Behind Caddy/Cloudflare the socket peer is the proxy, so the real address
    has to come from a header — but **X-Forwarded-For is not that header**.
    Proxies *append* to XFF rather than replacing it, so a client that sends
    ``X-Forwarded-For: 1.2.3.4`` arrives at the origin as
    ``1.2.3.4, <its real address>``. Keying on the first hop therefore let a
    brute-forcer mint a fresh bucket per request by varying a header, which is
    the entire login limit gone.

    So: prefer the header written by the outermost proxy — Cloudflare's
    ``CF-Connecting-IP``, which CF overwrites on every request and a client
    cannot influence — and fall back to XFF's first hop, then the socket peer,
    only when it is absent.

    **The assumption this rests on** is that the origin is reachable *only*
    through that proxy (here: a Cloudflare tunnel, so there is no direct route
    to the container). A deployment that exposes the origin directly would let
    a client forge ``CF-Connecting-IP`` too; point
    ``MM_TRUSTED_CLIENT_IP_HEADER`` at whatever its own edge sets, or to an
    empty string to key on XFF/peer as before.
    """
    trusted_header = (get_settings().trusted_client_ip_header or "").strip()
    if trusted_header:
        trusted = request.headers.get(trusted_header)
        if trusted and trusted.strip():
            return trusted.strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "anonymous"


limiter = Limiter(
    key_func=client_ip,
    enabled=get_settings().rate_limit_enabled,
    headers_enabled=True,
)


# Per-bucket limit values, evaluated per request so env overrides take effect
# without re-importing. Each is a callable returning a slowapi rate string.
def auth_limit() -> str:
    return get_settings().rate_limit_auth


def backup_limit() -> str:
    """Limit for the admin backup restore-upload endpoint. (The old ``import``
    bucket had one other user — folder library import — which is gone; spec
    §6.) ``rate_limit_import`` remains the backing setting/env key for
    compatibility."""
    return get_settings().rate_limit_import


# Back-compat alias — `routes/backup.py` historically imported this name.
import_limit = backup_limit


def sources_limit() -> str:
    return get_settings().rate_limit_sources


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Render a 429 in the app's standard ``{code, message, details}`` envelope,
    preserving slowapi's Retry-After / X-RateLimit-* headers."""
    response = JSONResponse(
        status_code=429,
        content={
            "code": "rate_limited",
            "message": "Too many requests. Please slow down and try again shortly.",
            "details": {"limit": str(exc.detail)},
        },
    )
    return request.app.state.limiter._inject_headers(
        response, request.state.view_rate_limit
    )

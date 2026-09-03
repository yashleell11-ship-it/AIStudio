"""Application configuration.

Single source of truth for runtime settings. Reads the shared
`config/settings.json` at the repo root and layers environment overrides on top.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

# backend/core/config.py -> parents[2] == repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
# Where user preferences (download/mature settings) are persisted. Overridable
# via MM_SETTINGS_PATH so the container can write to its /data volume: the
# packaged app lives at /app, where the repo-relative default resolves outside
# the writable tree (parents[2] == "/").
SETTINGS_PATH = (
    Path(os.environ["MM_SETTINGS_PATH"])
    if os.getenv("MM_SETTINGS_PATH")
    else REPO_ROOT / "config" / "settings.json"
)

APP_VERSION = "0.1.0"


class Settings(BaseModel):
    """Typed view over config/settings.json plus a few runtime-only fields."""

    # Tolerate unknown keys so settings.json can grow without breaking startup.
    model_config = {"extra": "allow"}

    project_name: str = "ManhwaManiacs"
    default_project: str = "ManhwaManiacs"

    # Adult/18+ content gate. Hidden by default; the user must explicitly
    # opt in (with an age confirmation on the client) before mature sources,
    # search results, and recommendations are shown. Persisted in
    # config/settings.json like the other user-facing preferences.
    mature_content_enabled: bool = False

    # Runtime-only (not persisted in settings.json).
    version: str = APP_VERSION
    db_path: str = str(REPO_ROOT / "backend" / "manhwamaniacs.db")
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    # TTL (minutes) for source_series_cache rows before a live connector
    # refetch is forced. Overridable via MM_SOURCE_CACHE_TTL_MINUTES.
    source_cache_ttl_minutes: int = 360

    # Hard ceiling (bytes) for a single proxied image/cover body. A hostile
    # allowlisted upstream can otherwise stream an unbounded "image" and OOM
    # the box (each page-image request used to buffer the entire body with no
    # cap). Overridable via MM_IMAGE_PROXY_MAX_BYTES.
    image_proxy_max_bytes: int = 25 * 1024 * 1024

    # Automatic update system
    update_workers: int = 1
    update_check_interval_minutes: int = 60

    # Authentication (P1). Runtime-only; overridable via env for deployment.
    # registration_enabled gates self-service signup *after* the bootstrap
    # admin exists (the very first account is always allowed, so the instance
    # can be claimed). Cookie flags default to secure/lax for production behind
    # HTTPS; local http dev sets MM_COOKIE_SECURE=false so the cookie is sent.
    registration_enabled: bool = True
    session_cookie_secure: bool = True
    session_cookie_samesite: str = "lax"

    # Inbound rate limiting (slowapi). Protects expensive/abusable endpoints
    # from brute force and abuse: auth (login/register), the admin backup
    # restore-upload, and source proxying (browse/search/image). rate_limit_import
    # is the (legacy-named) backing key for the backup bucket. Values are slowapi
    # rate strings
    # ("10/minute", "100/hour"); override each bucket via its env var. Disable
    # entirely with MM_RATE_LIMIT_ENABLED=false (e.g. for load tests). Limits are
    # keyed by client IP (X-Forwarded-For aware, since we run behind Caddy).
    rate_limit_enabled: bool = True
    rate_limit_auth: str = "10/minute"
    rate_limit_import: str = "5/minute"
    rate_limit_sources: str = "60/minute"
    # The request header carrying the real client IP, written by the *outermost*
    # proxy and therefore not client-controlled. Cloudflare's CF-Connecting-IP
    # is the default because that is the edge in front of this deployment.
    # X-Forwarded-For is NOT a safe default: proxies append to it rather than
    # replacing it, so its first hop is whatever the client sent. Set to an
    # empty string to fall back to X-Forwarded-For / the socket peer (e.g. a
    # deployment with no CDN in front). See core.rate_limit.client_ip.
    trusted_client_ip_header: str = "cf-connecting-ip"


@lru_cache
def get_settings() -> Settings:
    """Load settings once and cache them for the process lifetime."""
    data: dict = {}
    if SETTINGS_PATH.exists():
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))

    extra_origins = os.getenv("CORS_ORIGINS")
    if extra_origins:
        data["cors_origins"] = [o.strip() for o in extra_origins.split(",") if o.strip()]

    # Deployment overrides: point the database and downloads at the mounted
    # data volume (see docker-compose.yml) without editing settings.json.
    db_path_override = os.getenv("MM_DB_PATH")
    if db_path_override:
        data["db_path"] = db_path_override
    cache_ttl_override = os.getenv("MM_SOURCE_CACHE_TTL_MINUTES")
    if cache_ttl_override and cache_ttl_override.strip():
        data["source_cache_ttl_minutes"] = int(cache_ttl_override.strip())
    image_cap_override = os.getenv("MM_IMAGE_PROXY_MAX_BYTES")
    if image_cap_override and image_cap_override.strip():
        data["image_proxy_max_bytes"] = int(image_cap_override.strip())

    # Auth deployment overrides.
    reg_override = os.getenv("MM_REGISTRATION_ENABLED")
    if reg_override is not None:
        data["registration_enabled"] = reg_override.strip().lower() in {"1", "true", "yes", "on"}
    cookie_secure_override = os.getenv("MM_COOKIE_SECURE")
    if cookie_secure_override is not None:
        data["session_cookie_secure"] = cookie_secure_override.strip().lower() in {"1", "true", "yes", "on"}

    # Rate-limit deployment overrides.
    rate_limit_enabled_override = os.getenv("MM_RATE_LIMIT_ENABLED")
    if rate_limit_enabled_override is not None:
        data["rate_limit_enabled"] = rate_limit_enabled_override.strip().lower() in {"1", "true", "yes", "on"}
    for env_key, field in (
        ("MM_RATE_LIMIT_AUTH", "rate_limit_auth"),
        ("MM_RATE_LIMIT_IMPORT", "rate_limit_import"),
        ("MM_RATE_LIMIT_SOURCES", "rate_limit_sources"),
    ):
        value = os.getenv(env_key)
        if value and value.strip():
            data[field] = value.strip()
    client_ip_header_override = os.getenv("MM_TRUSTED_CLIENT_IP_HEADER")
    if client_ip_header_override is not None:
        # Empty is meaningful here ("no trusted header"), so this one tests for
        # presence rather than truthiness.
        data["trusted_client_ip_header"] = client_ip_header_override.strip()

    return Settings(**data)


def update_persisted_settings(**changes: object) -> Settings:
    """Merge ``changes`` into config/settings.json and refresh the cached
    Settings instance immediately, so callers see the new values on their
    very next ``get_settings()`` call -- no process restart required."""
    data: dict = {}
    if SETTINGS_PATH.exists():
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    data.update(changes)
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    get_settings.cache_clear()
    return get_settings()

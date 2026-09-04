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

    # TTL (minutes) for cached browse-listing pages (source_browse_cache).
    # Deliberately shorter than source_cache_ttl_minutes: a "latest"-sorted
    # grid reorders with every upstream chapter release, so six hours behind is
    # visibly wrong there, while one hour is invisible on a grid and still
    # absorbs virtually all repeat traffic. The TTL only controls refresh
    # cadence, not availability — expired rows are kept and served stale when
    # the connector is down. Overridable via MM_BROWSE_CACHE_TTL_MINUTES.
    browse_cache_ttl_minutes: int = 60
    # Row ceilings for the two connector caches; the oldest rows by fetched_at
    # are evicted past these. A browse row is one serialized page (~10-16 KB
    # for a 40-item grid) → 2000 rows ≈ 20-32 MB worst case. A series row is
    # ~1 KB of metadata (~10 KB with a long chapter list) → 20000 rows ≈
    # 20-200 MB worst case, in practice far less because browse write-through
    # rows carry no chapters. Overridable via MM_BROWSE_CACHE_MAX_ROWS /
    # MM_SOURCE_CACHE_MAX_ROWS.
    browse_cache_max_rows: int = 2000
    source_cache_max_rows: int = 20000
    # Warm the *next* browse page in the background after serving one, so
    # paging forward is instant. Never more than one page ahead, never on a
    # stale (connector-down) serve. Overridable via MM_BROWSE_PREFETCH_ENABLED;
    # the test suite disables it so no background threads outlive a test.
    browse_prefetch_enabled: bool = True

    # Novels (spec 2026-09-04-novels-design §2). OFF by default and NOT set by
    # the prod compose: production stays a manhwa site until the owner flips
    # MM_NOVELS_ENABLED on the VPS. When false, novel connectors are invisible
    # at every registry surface (listing, instantiation) and the /novels routes
    # are not mounted at all — the feature must be indistinguishable from
    # absent, not "present but forbidden".
    novels_enabled: bool = False
    # TTL (minutes) for novel_chapter_cache rows. Deliberately long (7 days):
    # published chapter text is immutable in practice, and a refetch is a full
    # upstream page scrape. Expired rows are still served stale when the
    # connector is down, like the browse cache. MM_NOVEL_CACHE_TTL_MINUTES.
    novel_cache_ttl_minutes: int = 7 * 24 * 60
    # Row ceiling for novel_chapter_cache; least-recently-USED rows are evicted
    # past it (the read path bumps last_used_at). A chapter is ~10-30 KB of
    # paragraph text → 10000 rows ≈ 100-300 MB worst case, in practice far
    # less. MM_NOVEL_CACHE_MAX_ROWS; <=0 disables the ceiling.
    novel_cache_max_rows: int = 10000

    # Hard ceiling (bytes) for a single proxied image/cover body. A hostile
    # allowlisted upstream can otherwise stream an unbounded "image" and OOM
    # the box (each page-image request used to buffer the entire body with no
    # cap). Overridable via MM_IMAGE_PROXY_MAX_BYTES.
    image_proxy_max_bytes: int = 25 * 1024 * 1024

    # Automatic update system
    update_workers: int = 1
    update_check_interval_minutes: int = 60
    # Guardrails for the full sweep (audit finding 14): without them a large
    # (attacker-inflatable) followed set plus a wedged upstream made a single
    # sweep run for hours of sequential 30s×3-retry fetches. Zero disables a
    # guard. Overridable via MM_UPDATE_SWEEP_SOURCE_BUDGET_SECONDS /
    # MM_UPDATE_SWEEP_DEADLINE_MINUTES.
    update_sweep_source_budget_seconds: int = 120
    update_sweep_deadline_minutes: int = 45
    # Per-(user, profile) ceiling on followed series — bounds the sweep's row
    # count at its source. Overridable via MM_MAX_FOLLOWS_PER_PROFILE.
    max_follows_per_profile: int = 1000

    # Authentication (P1). Runtime-only; overridable via env for deployment.
    # registration_enabled gates self-service signup *after* the bootstrap
    # admin exists (the very first account is always allowed, so the instance
    # can be claimed). Cookie flags default to secure/lax for production behind
    # HTTPS; local http dev sets MM_COOKIE_SECURE=false so the cookie is sent.
    registration_enabled: bool = True
    # Invite code gating self-service registration (MM_REGISTRATION_INVITE_CODE).
    # Semantics when a registration attempt arrives:
    #   * registration_enabled=false           -> refused entirely (403), except
    #     the bootstrap window below.
    #   * registration_enabled=true + code set -> POST /auth/register must carry
    #     a matching `invite_code` (compared in constant time); wrong/missing is
    #     a 403 with code `invite_code_invalid` / `invite_code_required`.
    #   * registration_enabled=true + no code  -> **OPEN registration. Anyone on
    #     the internet who can reach the host can create an account. Never run
    #     a public deployment in this state — set an invite code (see
    #     ops/vps/deploy.sh set-invite-code) or keep registration disabled.**
    # None/empty means "no code configured".
    registration_invite_code: str | None = None
    # Bootstrap window (MM_BOOTSTRAP_WINDOW_MINUTES): while the users table is
    # EMPTY, the first registration is allowed with no invite code (so the
    # instance can be claimed and that account becomes admin) — but only for
    # this many minutes after the empty table is first observed (recorded in
    # the `bootstrap_state` DB row). After that, an empty table no longer grants
    # uninvited registration: the normal registration_enabled + invite-code
    # rules apply, so a wiped database on a public host is not an indefinite
    # admin-takeover window. Set to 0 to disable uninvited bootstrap entirely
    # (claim the instance via `ops/vps/deploy.sh create-owner` instead).
    bootstrap_window_minutes: int = 30
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
    # /auth/register gets its own, tighter bucket (MM_RATE_LIMIT_REGISTER):
    # it is the invite-code brute-force surface, and account creation is rare
    # enough that a hard limit costs legitimate users nothing. Multiple limits
    # are combined with ";" (slowapi/limits parse_many), so a burst cap and an
    # hourly cap both apply.
    rate_limit_register: str = "5/minute;30/hour"
    # GET /auth/bootstrap-status is unauthenticated and announces exactly when
    # the bootstrap window is open — i.e. a free polling oracle for the moment
    # a freshly wiped instance can be claimed. A real client calls it about
    # once per app launch (to pick the login/register/claim UI), so the
    # per-minute burst never touches normal use — even a household of devices
    # behind one NAT — while a watcher polling every second or two trips it
    # within the first minute, and the hourly cap keeps sustained surveillance
    # slow and loud. (MM_RATE_LIMIT_BOOTSTRAP_STATUS)
    rate_limit_bootstrap_status: str = "30/minute;240/hour"
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
    for env_key, field in (
        ("MM_UPDATE_SWEEP_SOURCE_BUDGET_SECONDS", "update_sweep_source_budget_seconds"),
        ("MM_UPDATE_SWEEP_DEADLINE_MINUTES", "update_sweep_deadline_minutes"),
        ("MM_MAX_FOLLOWS_PER_PROFILE", "max_follows_per_profile"),
        ("MM_BOOTSTRAP_WINDOW_MINUTES", "bootstrap_window_minutes"),
        ("MM_BROWSE_CACHE_TTL_MINUTES", "browse_cache_ttl_minutes"),
        ("MM_BROWSE_CACHE_MAX_ROWS", "browse_cache_max_rows"),
        ("MM_SOURCE_CACHE_MAX_ROWS", "source_cache_max_rows"),
        ("MM_NOVEL_CACHE_TTL_MINUTES", "novel_cache_ttl_minutes"),
        ("MM_NOVEL_CACHE_MAX_ROWS", "novel_cache_max_rows"),
    ):
        value = os.getenv(env_key)
        if value and value.strip():
            data[field] = int(value.strip())
    # Novels kill switch (spec 2026-09-04-novels-design §2). Same bool parsing
    # as the other MM_* toggles; absent means the Settings default (False).
    novels_override = os.getenv("MM_NOVELS_ENABLED")
    if novels_override is not None:
        data["novels_enabled"] = novels_override.strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    prefetch_override = os.getenv("MM_BROWSE_PREFETCH_ENABLED")
    if prefetch_override is not None:
        data["browse_prefetch_enabled"] = prefetch_override.strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    # Auth deployment overrides.
    reg_override = os.getenv("MM_REGISTRATION_ENABLED")
    if reg_override is not None:
        data["registration_enabled"] = reg_override.strip().lower() in {"1", "true", "yes", "on"}
    invite_override = os.getenv("MM_REGISTRATION_INVITE_CODE")
    if invite_override is not None:
        # Presence-based: an empty value explicitly clears any persisted code
        # (i.e. "no code configured"), it does not mean "the code is ''".
        data["registration_invite_code"] = invite_override.strip() or None
    cookie_secure_override = os.getenv("MM_COOKIE_SECURE")
    if cookie_secure_override is not None:
        data["session_cookie_secure"] = cookie_secure_override.strip().lower() in {"1", "true", "yes", "on"}

    # Rate-limit deployment overrides.
    rate_limit_enabled_override = os.getenv("MM_RATE_LIMIT_ENABLED")
    if rate_limit_enabled_override is not None:
        data["rate_limit_enabled"] = rate_limit_enabled_override.strip().lower() in {"1", "true", "yes", "on"}
    for env_key, field in (
        ("MM_RATE_LIMIT_AUTH", "rate_limit_auth"),
        ("MM_RATE_LIMIT_REGISTER", "rate_limit_register"),
        ("MM_RATE_LIMIT_BOOTSTRAP_STATUS", "rate_limit_bootstrap_status"),
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

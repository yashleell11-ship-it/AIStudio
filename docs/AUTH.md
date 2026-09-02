# Authentication & the public-safe baseline

This document describes the authentication and authorization model introduced in
**Phase 3** (see [ROADMAP.md](ROADMAP.md)). It is the reference for how the
public deployment at manhwamaniacs.xyz is kept defensible.

> Scope note: the API is *closed by default* — every route needs a session, and
> destructive/admin operations need an admin session. Per-user read authorization
> is **done**, and is now **per-profile**: each profile has its own follows,
> reading progress, collections, bookmarks, and notifications, and cross-profile
> visibility is none by default (see
> [`superpowers/specs/2026-09-03-backend-source-native-design.md`](superpowers/specs/2026-09-03-backend-source-native-design.md)
> §5.3). `require_profile_context` guards every mutating route.

## Model at a glance

- **Passwords** are hashed with **argon2id** (`argon2-cffi`); plaintext is never
  stored. Weak/oversized passwords are rejected (`core/auth.py`).
- **Sessions** are opaque random tokens. Only their SHA-256 digest is persisted
  (`user_sessions.token_hash`); revocation deletes the row. Resolving a token
  lazily prunes it if expired.
- **Two transports, one session:**
  - **Web** receives the token as an **httpOnly cookie** (`mm_session`) set on
    login/register. The browser sends it automatically; the Next.js frontend
    adds `credentials: "include"` to every request.
  - **Mobile** reads the same token from the response body (`{ user, token }`)
    and sends it back as `Authorization: Bearer <token>`.
  - Logout on either transport revokes the same underlying session row.
- **The first registered account becomes the admin/owner** (bootstrap). After
  that, self-registration is gated by `MM_REGISTRATION_ENABLED`. (The old
  "claim NULL-owned rows from the single-user era" step is gone — the DB is
  wiped for the source-native rebuild and every owned row is
  `user_id`/`profile_id` NOT NULL.)

Implementation: `backend/services/auth_service.py` (business logic + the global
gate), `backend/core/auth.py` (password/token primitives), `backend/routes/auth.py`
(HTTP surface).

## The global authentication gate

Every route on `api_router` depends on `enforce_authentication`
(`backend/api/router.py`). A request is allowed through **only** if it is in the
public allowlist; otherwise an anonymous request gets `401 not_authenticated`.

### Public allowlist (no session required)

| Method | Path | Why it's public |
| --- | --- | --- |
| `GET`/`HEAD` | `/` | Landing page / JSON status probe — exposes no library or user data. |
| `GET`/`HEAD` | `/health` | Deploy + Caddy health probe. |
| `GET` | `/auth/bootstrap-status` | Lets the client show "create the first admin" vs a login form. Reports only `needs_bootstrap` + `registration_enabled`. |
| `POST` | `/auth/login` | Entry point. |
| `POST` | `/auth/register` | Entry point (self-gates: always allowed while zero users exist, then honours `MM_REGISTRATION_ENABLED`). |
| any | `/app/*` | APK distribution surface (download, version, changelog, landing assets). Public **by design** so a new user can install the app before they have an account; exposes no library or user data. |
| `OPTIONS` | any | CORS preflight carries no credentials. |

Everything else — the entire library, reader, sources, OCR, updates,
settings, and backup surface — requires a valid session.

### APK distribution is intentionally public

The `/app/*` routes (APK download, version manifest, changelog, install landing
page) stay public. Rationale: the mobile app itself is the front door to getting
an account, so gating the installer behind an account you can only create *in the
app* is circular. These routes serve only static distribution artifacts, never
library or user data. If you need to lock down distribution, put it behind the
edge (Caddy/Cloudflare Access) rather than the app session.

## Admin authorization

Destructive and administrative operations additionally require an **admin**
session via the `require_admin_user` dependency (a non-admin gets `403 forbidden`,
an anonymous caller `401`):

- `GET /backup/export`, `POST /backup/import`, `DELETE /backup/pending`

The previous stop-gap — an `MM_ADMIN_TOKEN` env var checked via an `X-Admin-Token`
header (`core/security.py`) — has been **removed**. Admin access is now purely a
property of the session's user (`users.is_admin`).

### Bootstrapping the first admin

On a fresh instance `GET /auth/bootstrap-status` returns `needs_bootstrap: true`.
The web login screen and the mobile login screen both detect this and present a
"create the first admin" form. The first `POST /auth/register` succeeds
regardless of `MM_REGISTRATION_ENABLED` and the resulting user is the admin.

## Inbound rate limiting

`slowapi` limits the expensive/abusable endpoints, keyed by the originating
client IP (X-Forwarded-For aware, since the app runs behind Caddy/Cloudflare). A
tripped limit returns `429 rate_limited` in the standard `{code, message,
details}` envelope with a `Retry-After` header. Buckets (all env-configurable):

| Bucket | Endpoints | Env var | Default |
| --- | --- | --- | --- |
| auth | `POST /auth/login`, `POST /auth/register` | `MM_RATE_LIMIT_AUTH` | `10/minute` |
| sources | `GET /sources/{id}/series` (browse/search), cover + page image proxies | `MM_RATE_LIMIT_SOURCES` | `60/minute` |

Set `MM_RATE_LIMIT_ENABLED=false` to disable limiting entirely (e.g. for load
tests). Storage is in-memory, so limits are enforced per worker process — a
brute-force/abuse backstop, not a precise cluster-wide quota.

## Environment variables

### Auth & sessions

| Var | Default | Purpose |
| --- | --- | --- |
| `MM_REGISTRATION_ENABLED` | `true` | Allow self-service signup *after* the bootstrap admin exists. Set `false` for an invite-only / single-household instance (the first account is always allowed so the instance can be claimed). |
| `MM_COOKIE_SECURE` | `true` | Set the session cookie `Secure` flag. Keep `true` in production (HTTPS). Set `false` only for local `http://` development, otherwise the browser will not send the cookie. |

### Rate limiting

| Var | Default | Purpose |
| --- | --- | --- |
| `MM_RATE_LIMIT_ENABLED` | `true` | Master on/off switch. |
| `MM_RATE_LIMIT_AUTH` | `10/minute` | Login/register bucket. |
| `MM_RATE_LIMIT_SOURCES` | `60/minute` | Source browse/search/image bucket. |

### Deploy paths & CORS (pre-existing)

| Var | Default | Purpose |
| --- | --- | --- |
| `MM_DB_PATH` | repo-relative | Point the SQLite database at the mounted data volume. |
| `MM_SETTINGS_PATH` | `config/settings.json` | Where user preferences persist (writable in the container). |
| `CORS_ORIGINS` | localhost dev origins | Comma-separated allowed origins. A wildcard `*` is rejected at startup outside debug mode. |

## Mobile client specifics

- The mobile app stores the bearer token in `flutter_secure_storage` and attaches
  it via a Dio interceptor. A `401` clears the token and routes back to login.
- **Release builds enforce an HTTPS base URL**: a non-HTTPS API URL is rejected
  in the production flavor (debug/dev may use `http://` for local testing).
- On cold start, a stored token is validated with `GET /auth/me`; a `401` means
  "not logged in" and the router sends the user to the login screen.

## Testing notes

- The suite's endpoint tests authenticate as a default in-memory admin (see the
  `default_auth` fixture in `backend/tests/conftest.py`), so they exercise the
  real routes without threading a login through each test. Tests that assert the
  real auth/authz behaviour (401/403, bootstrap, cookies, bearer) opt out with
  `@pytest.mark.real_auth` — see `tests/test_auth.py` and
  `tests/test_auth_enforcement.py`.
- The rate limiter is disabled for the suite except tests marked
  `@pytest.mark.rate_limit` (`tests/test_rate_limit.py`).

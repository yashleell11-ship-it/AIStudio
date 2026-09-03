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
- **The first registered account becomes the admin/owner**, but only while a
  time-boxed **bootstrap window** is open (`MM_BOOTSTRAP_WINDOW_MINUTES`,
  default 30, counted from the moment the users table is first observed
  empty). After that, an empty table no longer grants uninvited registration —
  claim the instance with `ops/vps/deploy.sh create-owner` instead. This
  bounds how long a freshly wiped public database is an open admin-takeover
  window. Exactly one admin is enforced at the database level (a partial
  unique index on `users.is_admin`), not just in application code.
- **Self-registration after bootstrap** is gated by `MM_REGISTRATION_ENABLED`
  (deployment default is `false` — see `ops/vps/docker-compose.yml`) and,
  when set, an invite code (`MM_REGISTRATION_INVITE_CODE`, compared in
  constant time). `GET /auth/bootstrap-status` tells the client which form to
  render (`bootstrap_open`, `invite_code_required`, `registration_open`) and
  never echoes the invite code itself. Manage the invite code with
  `ops/vps/deploy.sh set-invite-code [CODE|clear]`.
- (The old "claim NULL-owned rows from the single-user era" step is gone — the
  DB is wiped for the source-native rebuild and every owned row is
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

On a fresh instance `GET /auth/bootstrap-status` returns `needs_bootstrap: true`
and, while the bootstrap window is still open, `bootstrap_open: true`. The web
and mobile login screens key their "create the first admin" form on
`bootstrap_open`, not `needs_bootstrap` — an empty table with an expired window
no longer grants uninvited signup. While the window is open, `POST
/auth/register` succeeds with no invite code regardless of
`MM_REGISTRATION_ENABLED` and the resulting user is the admin; the
authoritative check happens inside a serialized claim transaction
(`AuthService.register(..., enforce_policy=True)`) so concurrent registrations
against an empty table can't each become admin. Once the window has closed,
claim the instance with `ops/vps/deploy.sh create-owner` (which runs inside the
container against the same DB and needs no window).

## Inbound rate limiting

`slowapi` limits the expensive/abusable endpoints, keyed by the originating
client IP (X-Forwarded-For aware, since the app runs behind Caddy/Cloudflare). A
tripped limit returns `429 rate_limited` in the standard `{code, message,
details}` envelope with a `Retry-After` header. Buckets (all env-configurable):

| Bucket | Endpoints | Env var | Default |
| --- | --- | --- | --- |
| auth | `POST /auth/login` | `MM_RATE_LIMIT_AUTH` | `10/minute` |
| register | `POST /auth/register` — its own tighter bucket, the invite-code brute-force surface | `MM_RATE_LIMIT_REGISTER` | `5/minute;30/hour` |
| bootstrap-status | `GET /auth/bootstrap-status` — unauthenticated, announces exactly when the bootstrap window is open | `MM_RATE_LIMIT_BOOTSTRAP_STATUS` | `30/minute;240/hour` |
| sources | `GET /sources/{id}/series` (browse/search), cover + page image proxies | `MM_RATE_LIMIT_SOURCES` | `60/minute` |
| import | `POST /backup/import` (backing key is legacy-named `rate_limit_import`) | `MM_RATE_LIMIT_IMPORT` | `5/minute` |

Set `MM_RATE_LIMIT_ENABLED=false` to disable limiting entirely (e.g. for load
tests). Storage is in-memory, so limits are enforced per worker process — a
brute-force/abuse backstop, not a precise cluster-wide quota.

## Environment variables

### Auth & sessions

| Var | Default | Purpose |
| --- | --- | --- |
| `MM_REGISTRATION_ENABLED` | `true` in code, `false` in `ops/vps/docker-compose.yml` | Allow self-service signup *after* the bootstrap admin exists. Production is closed; the owner account is created out-of-band with `ops/vps/deploy.sh create-owner`. |
| `MM_REGISTRATION_INVITE_CODE` | unset | When `MM_REGISTRATION_ENABLED=true`, require this code on `POST /auth/register` (outside the bootstrap window). Unset + enabled means **open registration** — never run a public deployment in that state. Manage via `ops/vps/deploy.sh set-invite-code`. |
| `MM_BOOTSTRAP_WINDOW_MINUTES` | `30` | How long, after the users table is first observed empty, an uninvited first registration is allowed and becomes admin. `0` disables uninvited bootstrap entirely (use `create-owner`). |
| `MM_COOKIE_SECURE` | `true` | Set the session cookie `Secure` flag. Keep `true` in production (HTTPS). Set `false` only for local `http://` development, otherwise the browser will not send the cookie. |

### Rate limiting

| Var | Default | Purpose |
| --- | --- | --- |
| `MM_RATE_LIMIT_ENABLED` | `true` | Master on/off switch. |
| `MM_RATE_LIMIT_AUTH` | `10/minute` | Login bucket. |
| `MM_RATE_LIMIT_REGISTER` | `5/minute;30/hour` | Register bucket. |
| `MM_RATE_LIMIT_BOOTSTRAP_STATUS` | `30/minute;240/hour` | Bootstrap-status polling bucket. |
| `MM_RATE_LIMIT_SOURCES` | `60/minute` | Source browse/search/image bucket. |
| `MM_RATE_LIMIT_IMPORT` | `5/minute` | Backup-restore-upload bucket. |

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

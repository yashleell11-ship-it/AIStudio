"""Authentication business logic: users and opaque sessions.

Household model: the first registered user becomes the admin/owner. Sessions are
opaque tokens whose SHA-256 is stored; revocation deletes the row. Web presents
the token as an httpOnly cookie, mobile as a bearer token — both resolve here.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Annotated

from fastapi import Cookie, Depends, Header, Request
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from core.auth import (
    generate_session_token,
    hash_password,
    hash_session_token,
    password_needs_rehash,
    validate_password_strength,
    verify_password,
)
from core.errors import AppError
from core.time_utils import utcnow
from database.models import User, UserSession
from database.session import get_db

SESSION_TTL = timedelta(days=7)
REMEMBER_ME_TTL = timedelta(days=90)

USERNAME_MIN = 3
USERNAME_MAX = 64
_USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{2,63}$")

# A fixed valid Argon2 hash used to equalize timing when a username does not
# exist, so login response time does not leak account existence.
_DUMMY_HASH = hash_password("mm-timing-equalizer-not-a-real-password")

# Per-user-state tables whose pre-multi-user rows are NULL-owned until the first
# admin registers and claims them (see register()). Fixed table names, not user
# input — safe to interpolate.
_OWNED_TABLES = (
    "user_series_state",
    "reading_progress",
    "chapter_progress",
    "reading_sessions",
    "bookmarks",
    "collections",
    "series_trackers",
    "update_notifications",
    "downloads",
)


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- users ---------------------------------------------------------------

    def user_count(self) -> int:
        return self.db.query(User).count()

    def get_user(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def get_by_username(self, username: str) -> User | None:
        normalized = (username or "").strip()
        if not normalized:
            return None
        return self.db.execute(
            select(User).where(User.username == normalized)
        ).scalar_one_or_none()

    def _validate_username(self, username: str) -> str:
        normalized = (username or "").strip()
        if not _USERNAME_RE.match(normalized):
            raise AppError(
                "Username must be 3-64 characters: letters, digits, and . _ - "
                "(starting with a letter or digit).",
                code="invalid_username",
                status_code=422,
            )
        return normalized

    def register(
        self,
        username: str,
        password: str,
        *,
        email: str | None = None,
        display_name: str | None = None,
    ) -> User:
        normalized = self._validate_username(username)
        pw_error = validate_password_strength(password)
        if pw_error:
            raise AppError(pw_error, code="weak_password", status_code=422)
        if self.get_by_username(normalized) is not None:
            raise AppError(
                "That username is already taken.",
                code="username_taken",
                status_code=409,
            )
        # The very first account is the admin/owner (bootstrap).
        is_admin = self.user_count() == 0
        user = User(
            username=normalized,
            email=(email or None),
            display_name=(display_name or None),
            password_hash=hash_password(password),
            is_admin=is_admin,
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        # The household owner inherits all pre-multi-user (NULL-owned) state, so
        # their existing library/progress/bookmarks survive the migration.
        if is_admin:
            self._claim_unowned_data(user.id)
        return user

    def _claim_unowned_data(self, user_id: int) -> None:
        """Assign every NULL-owned per-user row to ``user_id`` (idempotent)."""
        for table in _OWNED_TABLES:
            self.db.execute(
                text(f"UPDATE {table} SET user_id = :uid WHERE user_id IS NULL"),
                {"uid": user_id},
            )
        self.db.commit()

    def authenticate(self, username: str, password: str) -> User:
        """Return the user on valid credentials, else raise 401 (no enumeration)."""
        user = self.get_by_username(username)
        if user is None:
            # Equalize timing against the not-found path.
            verify_password(password, _DUMMY_HASH)
            raise AppError(
                "Invalid username or password.",
                code="invalid_credentials",
                status_code=401,
            )
        if not verify_password(password, user.password_hash):
            raise AppError(
                "Invalid username or password.",
                code="invalid_credentials",
                status_code=401,
            )
        if not user.is_active:
            raise AppError(
                "This account is disabled.", code="account_disabled", status_code=403
            )
        # Opportunistically upgrade the hash if params strengthened.
        if password_needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        user.last_login_at = utcnow()
        self.db.commit()
        return user

    def change_password(self, user: User, current: str, new_password: str) -> None:
        if not verify_password(current, user.password_hash):
            raise AppError(
                "Current password is incorrect.",
                code="invalid_credentials",
                status_code=401,
            )
        pw_error = validate_password_strength(new_password)
        if pw_error:
            raise AppError(pw_error, code="weak_password", status_code=422)
        user.password_hash = hash_password(new_password)
        self.db.commit()

    # --- sessions ------------------------------------------------------------

    def create_session(
        self,
        user: User,
        *,
        remember: bool = False,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[str, UserSession]:
        token = generate_session_token()
        session = UserSession(
            user_id=user.id,
            token_hash=hash_session_token(token),
            expires_at=utcnow() + (REMEMBER_ME_TTL if remember else SESSION_TTL),
            user_agent=(user_agent or None),
            ip_address=(ip_address or None),
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return token, session

    def resolve_session(self, token: str | None) -> User | None:
        """Return the live user for a raw token, or None. Deletes expired rows."""
        if not token:
            return None
        session = self.db.execute(
            select(UserSession).where(UserSession.token_hash == hash_session_token(token))
        ).scalar_one_or_none()
        if session is None:
            return None
        if session.expires_at <= utcnow():
            self.db.delete(session)
            self.db.commit()
            return None
        user = self.db.get(User, session.user_id)
        if user is None or not user.is_active:
            return None
        session.last_used_at = utcnow()
        self.db.commit()
        return user

    def revoke_token(self, token: str | None) -> bool:
        if not token:
            return False
        result = self.db.execute(
            delete(UserSession).where(UserSession.token_hash == hash_session_token(token))
        )
        self.db.commit()
        return bool(result.rowcount)

    def revoke_session_id(self, user_id: int, session_id: int) -> bool:
        result = self.db.execute(
            delete(UserSession).where(
                UserSession.id == session_id, UserSession.user_id == user_id
            )
        )
        self.db.commit()
        return bool(result.rowcount)

    def revoke_all(self, user_id: int, *, except_token: str | None = None) -> int:
        stmt = delete(UserSession).where(UserSession.user_id == user_id)
        if except_token:
            stmt = stmt.where(UserSession.token_hash != hash_session_token(except_token))
        result = self.db.execute(stmt)
        self.db.commit()
        return int(result.rowcount or 0)

    def list_sessions(self, user_id: int) -> list[UserSession]:
        return list(
            self.db.execute(
                select(UserSession)
                .where(UserSession.user_id == user_id)
                .order_by(UserSession.last_used_at.desc())
            ).scalars()
        )

    def cleanup_expired(self) -> int:
        result = self.db.execute(
            delete(UserSession).where(UserSession.expires_at <= utcnow())
        )
        self.db.commit()
        return int(result.rowcount or 0)


def get_auth_service(db: Annotated[Session, Depends(get_db)]) -> AuthService:
    return AuthService(db)


# --- request dependencies ----------------------------------------------------

# Web presents the session token as this httpOnly cookie; mobile presents it as
# an `Authorization: Bearer <token>` header. Both resolve to the same session.
SESSION_COOKIE_NAME = "mm_session"


def _extract_token(session_cookie: str | None, authorization: str | None) -> str | None:
    if session_cookie:
        return session_cookie
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            return value.strip()
    return None


def get_session_token(
    session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> str | None:
    """The raw session token for this request (cookie or bearer), or None."""
    return _extract_token(session_cookie, authorization)


def get_optional_user(
    auth: Annotated[AuthService, Depends(get_auth_service)],
    session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> User | None:
    """Resolve the current user from cookie or bearer token, or None if anonymous."""
    return auth.resolve_session(_extract_token(session_cookie, authorization))


def get_current_user(
    user: Annotated[User | None, Depends(get_optional_user)],
) -> User:
    """Require an authenticated user; raise 401 otherwise."""
    if user is None:
        raise AppError(
            "Authentication required.", code="not_authenticated", status_code=401
        )
    return user


def require_admin_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Require an authenticated admin; raise 403 for non-admins."""
    if not user.is_admin:
        raise AppError(
            "Administrator access required.", code="forbidden", status_code=403
        )
    return user


# --- global API authentication gate ------------------------------------------

# The ONLY routes reachable without a session. Everything else on the API
# requires authentication (see enforce_authentication, wired on api_router).
#   GET  /            landing page (HTML) / JSON status probe — no library data
#   GET  /health      deploy + Caddy health probe
#   GET  /auth/bootstrap-status  whether the first admin still needs creating
#   POST /auth/login  + /auth/register  entry points (register self-gates:
#                     always allowed while zero users exist; then honours
#                     registration_enabled)
# The /app/* distribution surface (APK download, version, changelog, landing
# assets) is public by design so new users can install the app before they have
# an account; it exposes no library or user data. Decision recorded in docs/AUTH.md.
_PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/"),
        ("HEAD", "/"),
        ("GET", "/health"),
        ("HEAD", "/health"),
        ("GET", "/auth/bootstrap-status"),
        ("POST", "/auth/login"),
        ("POST", "/auth/register"),
    }
)
_PUBLIC_PREFIXES: tuple[str, ...] = ("/app/",)


def _is_public_route(method: str, path: str) -> bool:
    if method == "OPTIONS":  # CORS preflight carries no credentials
        return True
    if path.startswith(_PUBLIC_PREFIXES):
        return True
    return (method, path) in _PUBLIC_ROUTES


def enforce_authentication(
    request: Request,
    user: Annotated[User | None, Depends(get_optional_user)],
) -> None:
    """Global gate applied to every API route: allow the public allowlist,
    otherwise require a valid session. Attaches the resolved user to
    ``request.state.user`` for downstream use."""
    if _is_public_route(request.method, request.url.path):
        request.state.user = user
        return
    if user is None:
        raise AppError(
            "Authentication required.", code="not_authenticated", status_code=401
        )
    request.state.user = user

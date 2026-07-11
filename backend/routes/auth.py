"""Authentication endpoints: register, login, logout, session management.

Web clients receive the session token as an httpOnly cookie (set automatically);
mobile clients read the same token from the response body and send it back as
``Authorization: Bearer <token>``. Both are the same opaque session — logout on
either revokes the row.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from core.config import get_settings
from core.errors import AppError
from database.models import User
from services.auth_service import (
    REMEMBER_ME_TTL,
    SESSION_COOKIE_NAME,
    SESSION_TTL,
    AuthService,
    get_auth_service,
    get_current_user,
    get_session_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])

AuthDep = Annotated[AuthService, Depends(get_auth_service)]
CurrentUser = Annotated[User, Depends(get_current_user)]


# --- schemas -----------------------------------------------------------------


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str | None = Field(default=None, max_length=255)
    display_name: str | None = Field(default=None, max_length=255)
    remember: bool = False


class LoginRequest(BaseModel):
    username: str
    password: str
    remember: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None
    display_name: str | None
    is_admin: bool
    created_at: datetime
    last_login_at: datetime | None


class AuthResponse(BaseModel):
    user: UserOut
    # Bearer token for mobile clients. Web clients ignore this and rely on the
    # httpOnly cookie set on the same response.
    token: str


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    user_agent: str | None
    ip_address: str | None
    current: bool = False


# --- helpers -----------------------------------------------------------------


def _set_session_cookie(response: Response, token: str, *, remember: bool) -> None:
    settings = get_settings()
    max_age = int((REMEMBER_ME_TTL if remember else SESSION_TTL).total_seconds())
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
    )


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    user_agent = request.headers.get("user-agent")
    # Behind Caddy/Cloudflare the real client IP is forwarded; fall back to the
    # socket peer for direct connections.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else None
    return user_agent, ip


# --- routes ------------------------------------------------------------------


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    auth: AuthDep,
) -> AuthResponse:
    """Create an account and start a session. The first account becomes admin.

    After the bootstrap account exists, self-registration requires
    ``registration_enabled`` (default on) — otherwise 403.
    """
    if auth.user_count() > 0 and not get_settings().registration_enabled:
        raise AppError(
            "Registration is disabled.",
            code="registration_disabled",
            status_code=403,
        )
    user = auth.register(
        body.username,
        body.password,
        email=body.email,
        display_name=body.display_name,
    )
    user_agent, ip = _client_meta(request)
    token, _ = auth.create_session(
        user, remember=body.remember, user_agent=user_agent, ip_address=ip
    )
    _set_session_cookie(response, token, remember=body.remember)
    return AuthResponse(user=UserOut.model_validate(user), token=token)


@router.post("/login", response_model=AuthResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    auth: AuthDep,
) -> AuthResponse:
    user = auth.authenticate(body.username, body.password)
    user_agent, ip = _client_meta(request)
    token, _ = auth.create_session(
        user, remember=body.remember, user_agent=user_agent, ip_address=ip
    )
    _set_session_cookie(response, token, remember=body.remember)
    return AuthResponse(user=UserOut.model_validate(user), token=token)


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    auth: AuthDep,
    _user: CurrentUser,
    token: Annotated[str | None, Depends(get_session_token)],
) -> Response:
    """Revoke the current session and clear the cookie."""
    auth.revoke_token(token)
    _clear_session_cookie(response)
    response.status_code = 204
    return response


@router.post("/logout-all", status_code=204)
def logout_all(
    response: Response,
    auth: AuthDep,
    user: CurrentUser,
) -> Response:
    """Revoke every session for the current user (sign out everywhere)."""
    auth.revoke_all(user.id)
    _clear_session_cookie(response)
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/change-password", status_code=204)
def change_password(
    body: ChangePasswordRequest,
    response: Response,
    auth: AuthDep,
    user: CurrentUser,
    token: Annotated[str | None, Depends(get_session_token)],
) -> Response:
    """Change the password and revoke all *other* sessions (keep this one)."""
    auth.change_password(user, body.current_password, body.new_password)
    auth.revoke_all(user.id, except_token=token)
    response.status_code = 204
    return response


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    auth: AuthDep,
    user: CurrentUser,
    token: Annotated[str | None, Depends(get_session_token)],
) -> list[SessionOut]:
    from core.auth import hash_session_token

    current_hash = hash_session_token(token) if token else None
    out: list[SessionOut] = []
    for session in auth.list_sessions(user.id):
        item = SessionOut.model_validate(session)
        item.current = session.token_hash == current_hash
        out.append(item)
    return out


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(
    session_id: int,
    response: Response,
    auth: AuthDep,
    user: CurrentUser,
) -> Response:
    revoked = auth.revoke_session_id(user.id, session_id)
    if not revoked:
        raise AppError("Session not found.", code="not_found", status_code=404)
    response.status_code = 204
    return response

"""Password hashing and session-token primitives.

Passwords are hashed with Argon2id (argon2-cffi defaults). Session tokens are
high-entropy random opaque strings — only their SHA-256 is persisted, so a fast
hash is appropriate there (unlike low-entropy passwords, which need Argon2).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError, VerifyMismatchError

# A malformed/foreign stored hash raises InvalidHashError, which is a ValueError
# rather than an Argon2Error, so it must be caught alongside the argon2 errors.
_HASH_ERRORS = (VerifyMismatchError, Argon2Error, InvalidHashError)

# Argon2id with library defaults (tuned, memory-hard). A single shared hasher is
# safe to reuse across threads.
_password_hasher = PasswordHasher()

# Minimum viable password policy (rejected: email verification / complexity
# rules beyond a length floor, per the locked design).
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 4096  # guard against argon2 DoS via absurdly long inputs


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time-ish verify; returns False on any mismatch or malformed hash."""
    try:
        _password_hasher.verify(password_hash, password)
        return True
    except _HASH_ERRORS:
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """True if the stored hash used weaker params than the current defaults."""
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except _HASH_ERRORS:
        return True


def validate_password_strength(password: str) -> str | None:
    """Return an error message if the password is unacceptable, else None."""
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > MAX_PASSWORD_LENGTH:
        return "Password is too long."
    return None


def generate_session_token() -> str:
    """A URL-safe opaque token (~256 bits of entropy)."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """SHA-256 hex of the raw token — what we persist and look up by."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)

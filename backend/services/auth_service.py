"""Authentication business logic: users and opaque sessions.

Household model: the first registered user becomes the admin/owner. Sessions are
opaque tokens whose SHA-256 is stored; revocation deletes the row. Web presents
the token as an httpOnly cookie, mobile as a bearer token — both resolve here.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from hmac import compare_digest
from typing import Annotated

from fastapi import Cookie, Depends, Header, Request
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.auth import (
    generate_session_token,
    hash_password,
    hash_session_token,
    password_needs_rehash,
    validate_password_strength,
    verify_password,
)
from core.config import get_settings
from core.errors import AppError
from core.time_utils import utcnow
from database.models import BootstrapState, ChapterOcr, User, UserSession
from database.session import get_db

logger = logging.getLogger("manhwamaniacs.auth")

SESSION_TTL = timedelta(days=7)
REMEMBER_ME_TTL = timedelta(days=90)

# A login is the only thing that ever inserts a session row, and a row lives
# 7 days (90 with remember-me), so without a ceiling a client stuck in a
# re-login loop — or anyone holding one valid password — grows the table until
# the rows age out a quarter later. A household member reads on a handful of
# devices; the oldest session past this is evicted at the next login.
MAX_SESSIONS_PER_USER = 10

USERNAME_MIN = 3
USERNAME_MAX = 64
_USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{2,63}$")

# A fixed valid Argon2 hash used to equalize timing when a username does not
# exist, so login response time does not leak account existence.
_DUMMY_HASH = hash_password("mm-timing-equalizer-not-a-real-password")

class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- users ---------------------------------------------------------------

    def user_count(self) -> int:
        return self.db.query(User).count()

    # --- bootstrap window ----------------------------------------------------
    #
    # An empty users table on a public host is an admin-takeover window: the
    # first registration becomes admin, with no invite code. These methods
    # bound that window to Settings.bootstrap_window_minutes from the moment
    # the empty table is first observed (recorded in the bootstrap_state
    # singleton row — in the DB, so the marker travels with the data it
    # describes: restores, wipes, and reset-accounts all stay consistent).

    def bootstrap_window_deadline(self) -> datetime | None:
        """The instant uninvited bootstrap registration stops being allowed,
        or None when it does not apply (users already exist).

        Lazily stamps ``bootstrap_state.empty_since`` the first time an empty
        users table is observed.
        """
        if self.user_count() > 0:
            return None
        state = self.db.get(BootstrapState, 1)
        if state is None:
            state = BootstrapState(id=1, empty_since=utcnow())
            self.db.add(state)
            try:
                self.db.commit()
            except IntegrityError:
                # Two requests observed the empty table at the same instant and
                # both tried to create the singleton row; keep the winner's.
                self.db.rollback()
                state = self.db.get(BootstrapState, 1)
                if state is None:
                    # Gone again already: the bootstrap claim committed between
                    # our rollback and re-read, so users now exist and the
                    # window no longer applies.
                    return None
                return state.empty_since + timedelta(
                    minutes=max(get_settings().bootstrap_window_minutes, 0)
                )
            logger.warning(
                "users table is empty: bootstrap registration is OPEN — the "
                "first account to register becomes admin (window closes at %s, "
                "MM_BOOTSTRAP_WINDOW_MINUTES=%d).",
                (state.empty_since
                 + timedelta(minutes=get_settings().bootstrap_window_minutes)
                 ).isoformat(),
                get_settings().bootstrap_window_minutes,
            )
        return state.empty_since + timedelta(
            minutes=max(get_settings().bootstrap_window_minutes, 0)
        )

    def bootstrap_window_open(self) -> bool:
        """True while the users table is empty AND inside the bootstrap window,
        i.e. an uninvited registration right now would be allowed (and become
        admin). With ``bootstrap_window_minutes=0`` this is never True."""
        deadline = self.bootstrap_window_deadline()
        return deadline is not None and utcnow() < deadline

    def ensure_registration_allowed(self, invite_code: str | None) -> None:
        """Gate a registration attempt; raise AppError (403) if it may not
        proceed.

        Order of evaluation:
          1. Empty users table with the bootstrap window still open — allowed
             uninvited (the account will be the admin/owner). This is the only
             path that bypasses ``registration_enabled``.
          2. Otherwise ``registration_enabled`` must be on
             (403 ``registration_disabled``).
          3. If an invite code is configured, the supplied one must match —
             compared in constant time (403 ``invite_code_required`` /
             ``invite_code_invalid``).

        This is the *pre-flight* check the route runs before the expensive
        Argon2 hash. It reads shared state without any lock, so its verdict
        can go stale under concurrency — the authoritative decision is
        re-taken inside :meth:`register`'s claim transaction
        (``enforce_policy=True``).
        """
        if self.user_count() == 0:
            if self.bootstrap_window_open():
                return
            logger.warning(
                "users table is empty but the bootstrap window has EXPIRED: "
                "refusing uninvited registration (re-arm with "
                "ops/vps/deploy.sh reset-accounts, or claim the instance with "
                "create-owner)."
            )
        self._ensure_invited(invite_code)

    def _ensure_invited(self, invite_code: str | None) -> None:
        """The post-bootstrap registration rules: ``registration_enabled`` must
        be on, and a configured invite code must match (constant time)."""
        settings = get_settings()
        if not settings.registration_enabled:
            raise AppError(
                "Registration is disabled.",
                code="registration_disabled",
                status_code=403,
            )
        configured = settings.registration_invite_code
        if configured:
            if not invite_code:
                raise AppError(
                    "An invite code is required to register.",
                    code="invite_code_required",
                    status_code=403,
                )
            if not compare_digest(
                invite_code.encode("utf-8"), configured.encode("utf-8")
            ):
                raise AppError(
                    "Invalid invite code.",
                    code="invite_code_invalid",
                    status_code=403,
                )

    def _bootstrap_window_open_locked(self) -> bool:
        """:meth:`bootstrap_window_open` re-read *inside* the claim transaction
        (see :meth:`register`).

        MUST NOT commit — a commit would release the ``BEGIN IMMEDIATE`` lock
        mid-claim — so unlike the pre-flight it never lazily stamps
        ``bootstrap_state``: an empty table with no marker row means the window
        would start *now*, which is open iff a nonzero window is configured
        (matching :meth:`bootstrap_window_open` semantics for minutes=0).
        """
        state = self.db.get(BootstrapState, 1)
        empty_since = state.empty_since if state is not None else utcnow()
        deadline = empty_since + timedelta(
            minutes=max(get_settings().bootstrap_window_minutes, 0)
        )
        return utcnow() < deadline

    def _may_claim_admin_locked(
        self, *, window_open: bool, enforce_policy: bool
    ) -> bool:
        """Whether an empty users table may be claimed as admin/owner right now.

        Inside the window: by whoever reaches the host first — that IS the
        bootstrap. Past it: only by the operator, i.e. the CLI
        (``enforce_policy=False``, ``ops/vps/deploy.sh create-owner``) or,
        where the deployment configures an invite code, whoever presents it
        (:meth:`_ensure_invited` has verified it before this decides).
        Otherwise nobody — because "the ordinary rules then apply" bounds
        *registration*, not the *admin* claim: with registration enabled and no
        invite code (the live posture, deliberately) those rules admit the
        whole internet, so ownership of a wiped, restored-empty or
        reset-accounts instance would fall to the first stranger to POST
        /auth/register, which is the takeover the bounded window exists to
        prevent.
        """
        if window_open or not enforce_policy:
            return True
        return bool(get_settings().registration_invite_code)

    def _ensure_registration_allowed_locked(
        self, invite_code: str | None, user_count: int, window_open: bool
    ) -> None:
        """Authoritative re-run of the registration rules *inside* the claim
        transaction (see :meth:`register`), with ``window_open`` read under the
        same lock by :meth:`_bootstrap_window_open_locked`.
        """
        if user_count == 0 and window_open:
            return
        self._ensure_invited(invite_code)
        if user_count == 0 and not self._may_claim_admin_locked(
            window_open=window_open, enforce_policy=True
        ):
            # Clearing _ensure_invited is not enough to become the owner — it
            # clears everyone when registration is open with no invite code.
            # Refuse the registration outright rather than create the account:
            # a non-admin first user would leave the instance unclaimable
            # (the owner could no longer bootstrap), so the empty table is
            # kept intact for create-owner / reset-accounts.
            raise AppError(
                "This instance's bootstrap window has closed; it must be "
                "claimed by its operator (ops/vps/deploy.sh create-owner).",
                code="bootstrap_window_expired",
                status_code=403,
            )

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

    def _begin_immediate_claim(self) -> None:
        """Open a SQLite write transaction NOW (``BEGIN IMMEDIATE``) on this
        session's connection.

        pysqlite defers ``BEGIN`` until the first DML, so plain SELECTs run in
        autocommit — which made the bootstrap claim a textbook check-then-act
        race: every concurrent request could observe ``user_count() == 0``
        before any of them committed. Taking the write lock up front makes
        everything from the count to the commit one atomic unit; a concurrent
        claimer blocks inside ``BEGIN IMMEDIATE`` (up to the connection's busy
        timeout, 5s) and then reads the winner's committed row.

        Deliberately scoped to the registration path only — an
        ``isolation_level="IMMEDIATE"`` connect arg would turn *every* ORM
        transaction in the process into an eager write lock and serialize
        read-mostly requests against the update sweep on this 2-vCore box.
        Here the lock is taken *after* Argon2 hashing and held only for a few
        sub-millisecond statements. IMMEDIATE also cannot deadlock the sweep's
        writers: SQLite has a single writer lock, waiters queue on the busy
        timeout, and (unlike a deferred read-then-write transaction) we never
        upgrade a read lock into a write lock.
        """
        conn = self.db.connection()
        raw = getattr(conn.connection, "dbapi_connection", None)
        if raw is not None and getattr(raw, "in_transaction", False):
            # A DBAPI-level transaction is already open (an earlier statement
            # in this session wrote something), so the write lock is already
            # held/pending and a second BEGIN would error.
            return
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    def register(
        self,
        username: str,
        password: str,
        *,
        email: str | None = None,
        display_name: str | None = None,
        invite_code: str | None = None,
        enforce_policy: bool = False,
    ) -> User:
        """Create an account; the first account in an empty users table becomes
        the admin/owner (bootstrap) — but only while that claim is still open
        (see :meth:`_may_claim_admin_locked`); past the window a self-service
        attempt is refused rather than promoted.

        The whole claim — "is the table empty?" → INSERT → consume the
        ``bootstrap_state`` marker — runs inside one ``BEGIN IMMEDIATE`` write
        transaction, so concurrent registrations serialize: exactly one can
        observe the empty table, and every loser re-observes a table that
        already has its owner.

        ``enforce_policy=True`` (the HTTP route) re-runs the registration
        permission rules *inside* that transaction. Without it, a request that
        raced the bootstrap claim and lost would fall through and be created
        as a regular user even with ``registration_enabled`` off — a quieter
        cousin of the multi-admin bug. The default (False) serves the operator
        CLI (``ops/vps/deploy.sh create-owner``), which deliberately bypasses
        the self-service rules; it still gets the serialized claim and the
        single-admin index.
        """
        normalized = self._validate_username(username)
        pw_error = validate_password_strength(password)
        if pw_error:
            raise AppError(pw_error, code="weak_password", status_code=422)
        if self.get_by_username(normalized) is not None:
            # Optimistic pre-check for the friendly 409; the UNIQUE constraint
            # (caught below) is the authoritative guard under concurrency.
            raise AppError(
                "That username is already taken.",
                code="username_taken",
                status_code=409,
            )
        # Argon2 is deliberately slow (CPU-bound, ~100ms): hash BEFORE taking
        # the write lock so concurrent registrations do not serialize the
        # whole database behind password hashing.
        password_hash = hash_password(password)

        self._begin_immediate_claim()
        try:
            # Authoritative: read under the write lock, so a lost race sees
            # the winner's committed account.
            count = self.user_count()
            # Read the window once for the whole claim: the policy re-check and
            # the admin bit must not be able to disagree across its deadline.
            window_open = count == 0 and self._bootstrap_window_open_locked()
            if enforce_policy:
                self._ensure_registration_allowed_locked(
                    invite_code, count, window_open
                )
            # The very first account is the admin/owner (bootstrap) — but only
            # when it is entitled to claim the instance (see
            # _may_claim_admin_locked); otherwise the check above already
            # refused it.
            is_admin = count == 0 and self._may_claim_admin_locked(
                window_open=window_open, enforce_policy=enforce_policy
            )
            user = User(
                username=normalized,
                email=(email or None),
                display_name=(display_name or None),
                password_hash=password_hash,
                is_admin=is_admin,
                is_active=True,
            )
            self.db.add(user)
            if is_admin:
                # Consume the bootstrap claim token in the SAME transaction as
                # the INSERT: the window is closed by the act of claiming it,
                # not by a later observation — and a later wipe starts a
                # *fresh* window instead of inheriting this stale timestamp.
                state = self.db.get(BootstrapState, 1)
                if state is not None:
                    self.db.delete(state)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            detail = str(exc.orig or exc)
            # SQLite reports a partial-unique-index violation by column
            # ("UNIQUE constraint failed: users.is_admin"); match the index
            # name too in case a future SQLite phrases it that way.
            if "users.is_admin" in detail or "uq_users_single_admin" in detail:
                # Belt-and-braces: the partial unique index refused a second
                # admin row. Unreachable while the claim above is serialized,
                # but a lost race must fail loudly — never mint a second owner.
                raise AppError(
                    "This instance already has an owner.",
                    code="bootstrap_already_claimed",
                    status_code=409,
                ) from exc
            if "users.username" in detail:
                raise AppError(
                    "That username is already taken.",
                    code="username_taken",
                    status_code=409,
                ) from exc
            raise
        except Exception:
            # Includes AppError from the locked policy re-check: roll back so
            # the write lock is released before the error propagates.
            self.db.rollback()
            raise
        if is_admin:
            logger.info(
                "Bootstrap complete: first account %r registered and is the "
                "admin/owner.",
                normalized,
            )
        self.db.refresh(user)
        # No "claim NULL-owned rows" step: the DB is a fresh source-native
        # baseline (spec §5.3) — every per-profile table is user_id/profile_id
        # NOT NULL, so there is nothing unowned to adopt.
        return user

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

    def change_password(
        self,
        user: User,
        current: str,
        new_password: str,
        *,
        keep_token: str | None = None,
    ) -> None:
        """Rotate the password and drop every other session, atomically.

        The rotation and the revocation are ONE transaction because the second
        is what makes the first mean anything: a password change is how a
        reader responds to a token they think has leaked, and with two commits
        an error (or a lost SQLite write) between them leaves the new password
        in place while every session minted with the old one keeps working —
        the exact sessions the change exists to kill, and silently, since the
        caller has already been told the password changed.

        ``keep_token`` is the caller's own session, spared so the person doing
        it is not signed out of the device they are typing on; omit it (the
        operator/CLI path) and every session goes.
        """
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
        stmt = delete(UserSession).where(UserSession.user_id == user.id)
        if keep_token:
            stmt = stmt.where(
                UserSession.token_hash != hash_session_token(keep_token)
            )
        self.db.execute(stmt.execution_options(synchronize_session=False))
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
        # Flush first so the row this login just minted has an id and counts as
        # one of the survivors — otherwise the cap would evict a live device to
        # make room for a session the trim cannot see yet.
        self.db.flush()
        # A login is the right place to pay for table hygiene: it is rare, it
        # is rate-limited, and it is already a write — so both sweeps ride this
        # transaction and cost no extra commit. The global one catches rows
        # belonging to accounts that stopped visiting altogether, which the
        # per-user trim below can never reach.
        self._delete_expired_sessions()
        self._evict_surplus_sessions(user.id)
        self.db.commit()
        self.db.refresh(session)
        return token, session

    def _evict_surplus_sessions(self, user_id: int) -> None:
        """Keep only the ``MAX_SESSIONS_PER_USER`` newest *live* sessions of a
        user; everything else of theirs — surplus or expired — goes.

        Expired rows are excluded from the survivors rather than counted among
        them: a 7-day session that died yesterday is "newer" than a 90-day
        remember-me from last month, so counting it would evict the device the
        reader is still using in favour of a token nobody can present.
        """
        keep = (
            select(UserSession.id)
            .where(
                UserSession.user_id == user_id,
                UserSession.expires_at > utcnow(),
            )
            # id breaks the tie: two logins can share a created_at timestamp,
            # and an unstable order would evict an arbitrary one of them.
            .order_by(UserSession.created_at.desc(), UserSession.id.desc())
            .limit(MAX_SESSIONS_PER_USER)
            .scalar_subquery()
        )
        self.db.execute(
            delete(UserSession)
            .where(UserSession.user_id == user_id, UserSession.id.not_in(keep))
            .execution_options(synchronize_session=False)
        )

    def resolve_session(self, token: str | None) -> User | None:
        """Return the live user for a raw token, or None. Deletes expired rows."""
        if not token:
            return None
        self._maybe_sweep_expired()
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
        self._touch(session)
        return user

    # Only bump `last_used_at` once it is this stale. Every authenticated
    # request passes through here, and each page image is its own request: a
    # client downloading a 40-page chapter would otherwise open 40 write
    # transactions, and a 100-chapter series 4,000 — all serialised by SQLite's
    # single writer and contending with the update scheduler. The column feeds
    # the "last used" column of the sessions screen and nothing else; expiry is
    # `expires_at`, which this does not touch. Minute-granularity is plenty.
    _TOUCH_INTERVAL_SECONDS = 60

    def _touch(self, session: UserSession) -> None:
        now = utcnow()
        last = session.last_used_at
        if last is not None and (now - last).total_seconds() < self._TOUCH_INTERVAL_SECONDS:
            # Nothing was modified, so there is nothing to commit -- returning
            # here is what makes a read request read-only.
            return
        session.last_used_at = now
        self.db.commit()

    # An expired row is otherwise deleted only by main.prune_expired_sessions at
    # startup or by presenting that exact dead token again, so a remember-me
    # token nobody ever presents again sits in the table for its whole 90 days
    # and across every restartless week. Sweeping every Nth resolve keeps the
    # table swept while the process runs. It rides on request traffic rather
    # than a thread of its own because the sweep must not become another writer
    # racing the update scheduler for SQLite's single write lock: the probe is
    # an index-only lookup on ix_sessions_expires_at, and only a hit opens a
    # write transaction, so ordinary read traffic (one request per chapter
    # page) stays read-only.
    _SWEEP_EVERY_RESOLVES = 20
    _resolves_since_sweep = 0

    def _maybe_sweep_expired(self) -> None:
        # Class-level, not per-instance: AuthService is constructed per request.
        AuthService._resolves_since_sweep += 1
        if AuthService._resolves_since_sweep < self._SWEEP_EVERY_RESOLVES:
            return
        AuthService._resolves_since_sweep = 0
        expired = self.db.execute(
            select(UserSession.id).where(UserSession.expires_at <= utcnow()).limit(1)
        ).first()
        if expired is not None:
            self.cleanup_expired()

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

    def _delete_expired_sessions(self) -> int:
        """Delete every session past its expiry. Does NOT commit — the caller
        owns the transaction, so this can join one that is already open."""
        result = self.db.execute(
            delete(UserSession)
            .where(UserSession.expires_at <= utcnow())
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount or 0)

    def cleanup_expired(self) -> int:
        removed = self._delete_expired_sessions()
        self.db.commit()
        return removed

    # --- account administration ----------------------------------------------
    #
    # The other half of open registration: anyone who can reach this host can
    # create an account, so the owner needs a way to take one away again.

    def count_live_sessions(self, user_id: int) -> int:
        """Unexpired session rows — i.e. devices this account is signed in on.

        Expired rows are excluded because they are indistinguishable from
        deleted ones to every client: they cannot authenticate, and the next
        login or sweep removes them. Counting them would show the owner a
        device count that quietly shrinks on its own."""
        return int(
            self.db.execute(
                select(func.count())
                .select_from(UserSession)
                .where(
                    UserSession.user_id == user_id,
                    UserSession.expires_at > utcnow(),
                )
            ).scalar_one()
        )

    def list_users_with_session_counts(self) -> list[tuple[User, int]]:
        """Every account with its live session count, oldest account first.

        The counts come from one grouped LEFT JOIN rather than a query per
        row: the members screen lists every account on the instance, and a
        per-row count is the N+1 that turns one page render into one query per
        person on it."""
        live = (
            select(UserSession.user_id, func.count().label("live"))
            .where(UserSession.expires_at > utcnow())
            .group_by(UserSession.user_id)
            .subquery()
        )
        rows = self.db.execute(
            select(User, func.coalesce(live.c.live, 0))
            .outerjoin(live, live.c.user_id == User.id)
            .order_by(User.id)
        ).all()
        return [(user, int(count)) for user, count in rows]

    def get_managed_user(self, actor: User, user_id: int) -> User:
        """The account an admin may act on, or raise.

        An admin is refused its own account: the single-admin index means there
        is no second owner to hand the instance to, and ``bootstrap_state`` was
        consumed by the original claim — so a self-delete (or a self-disable,
        which is a delete of the only key) leaves an instance nobody can
        administer and nobody can re-claim.
        """
        if user_id == actor.id:
            raise AppError(
                "An administrator cannot disable or delete its own account.",
                code="cannot_manage_self",
                status_code=400,
            )
        target = self.get_user(user_id)
        if target is None:
            raise AppError("User not found.", code="not_found", status_code=404)
        return target

    def set_user_active(self, user: User, active: bool) -> User:
        """Enable or disable an account.

        Disabling drops the account's sessions as well as flipping the flag.
        ``resolve_session`` already refuses an inactive user, so the kick is
        immediate either way — but leaving the rows behind would mean
        re-enabling the account silently resurrects every token it ever held,
        including whatever got it disabled.
        """
        user.is_active = active
        if not active:
            self.db.execute(delete(UserSession).where(UserSession.user_id == user.id))
        self.db.commit()
        self.db.refresh(user)
        return user

    def delete_user(self, user: User) -> None:
        """Delete an account and everything owned by it.

        One ORM delete is the whole cascade: the ``sessions`` relationship
        removes the tokens, and ``reading_profiles`` is ``ON DELETE CASCADE``
        from ``users`` — which in turn cascades every per-profile table
        (followed_series, chapter_progress, bookmarks, collections, tags,
        notifications, ...), exactly as ProfileService.delete_profile relies on
        (``PRAGMA foreign_keys=ON``, set in database.session).

        ``chapter_ocr`` is the one table that keeps its rows: it is a global
        cache, one row per chapter, that every account reads — deleting a
        member would otherwise delete transcripts for everyone. Only the
        attribution is cleared, and it has to be cleared explicitly because
        ``contributed_by_user_id`` is a bare Integer with no foreign key to
        cascade through: SQLite reuses rowids, so an id left behind would end
        up naming whichever future account inherits it.
        """
        self.db.execute(
            update(ChapterOcr)
            .where(ChapterOcr.contributed_by_user_id == user.id)
            .values(contributed_by_user_id=None)
            .execution_options(synchronize_session=False)
        )
        self.db.delete(user)
        self.db.commit()


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
#   POST /auth/login  + /auth/register  entry points (register self-gates via
#                     AuthService.ensure_registration_allowed: uninvited only
#                     while zero users exist AND the bootstrap window is open;
#                     then honours registration_enabled + the invite code)
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

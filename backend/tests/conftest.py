from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.models import Base
from services.download_manager import reset_download_manager_for_tests
from services.ocr_engine import _clear_easyocr_cache
from services.ocr_pipeline import reset_ocr_manager_for_tests
from services.update_scheduler import reset_update_manager_for_tests


@pytest.fixture
def db_engine(tmp_path: Path):
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def reset_ocr_manager():
    """Ensure the global OCR manager and EasyOCR cache are reset before/after every test."""
    _clear_easyocr_cache()
    reset_ocr_manager_for_tests()
    yield
    _clear_easyocr_cache()
    reset_ocr_manager_for_tests()


@pytest.fixture(autouse=True)
def reset_update_manager():
    """Ensure the global update manager is reset before and after every test."""
    reset_update_manager_for_tests()
    yield
    reset_update_manager_for_tests()


@pytest.fixture(autouse=True)
def reset_download_manager():
    """Reset the global download-manager singleton before and after every test.
    Without this, a manager started by one test can pick up (and transition) a
    later test's freshly-queued downloads, making assertions order-dependent."""
    reset_download_manager_for_tests(None)
    yield
    reset_download_manager_for_tests(None)


@pytest.fixture(autouse=True)
def default_auth(monkeypatch, request):
    """The whole API now requires a session (services.auth_service.
    enforce_authentication on api_router). For the suite, resolve every request
    to a default admin so existing endpoint tests keep working without threading
    real login flows through each one.

    Implementation: monkeypatch ``AuthService.resolve_session`` (evaluated per
    request, so it also covers module-level ``TestClient(app)`` instances) to
    return an *in-memory* admin with ``id is None``. That id is deliberate: the
    per-user query scoping (``WHERE user_id = :id``) then renders ``IS NULL`` and
    matches exactly the legacy/anonymous rows these tests seed directly — i.e.
    the pre-auth behaviour, minus the 401 gate. Nothing is persisted, so tests
    that seed owner-less rows need no changes.

    Tests that exercise real authentication/authorization opt out with
    ``@pytest.mark.real_auth`` (then unauthenticated == 401, and they drive
    register/login themselves)."""
    if request.node.get_closest_marker("real_auth"):
        yield
        return

    from database.models import User
    from services import auth_service

    def _resolve_default_admin(self, token):  # noqa: ARG001 - token ignored in tests
        return User(
            username="testadmin",
            password_hash="x",
            is_admin=True,
            is_active=True,
        )

    monkeypatch.setattr(
        auth_service.AuthService, "resolve_session", _resolve_default_admin
    )
    yield


@pytest.fixture(autouse=True)
def rate_limit_toggle(request, monkeypatch):
    """The inbound rate limiter is ON by default in production. Disable it for
    the suite so the many rapid requests endpoint tests make never trip a 429;
    tests that specifically exercise limiting opt in with ``@pytest.mark.
    rate_limit`` (and get a fresh limiter storage)."""
    from core.rate_limit import limiter

    enabled = request.node.get_closest_marker("rate_limit") is not None
    monkeypatch.setattr(limiter, "enabled", enabled)
    if enabled and hasattr(limiter, "reset"):
        limiter.reset()
    yield


@pytest.fixture(autouse=True)
def allow_tmp_imports(tmp_path_factory, monkeypatch):
    """Library import containment (LibraryService._allowed_import_roots) rejects
    any folder outside the configured import roots. Endpoint tests import
    fixtures created under pytest's tmp directories, so register that base as an
    allowed import root for the whole suite. Dedicated containment tests still
    prove that paths *outside* this base (e.g. ``/etc``, ``/``) are rejected.

    Set it through the env var and clear the settings cache so the allowance
    survives the ``get_settings.cache_clear()`` that some client fixtures do."""
    from core.config import get_settings

    base = str(tmp_path_factory.getbasetemp())
    monkeypatch.setenv("MM_IMPORT_ROOTS", base)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

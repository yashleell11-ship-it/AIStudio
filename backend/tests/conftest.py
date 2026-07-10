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
def admin_auth(monkeypatch):
    """Admin endpoints (backup, library import) are gated by
    ``core.security.require_admin``. Configure a token for the whole suite and
    make every TestClient send it by default, so gating those routes doesn't
    require editing each test. Individual tests can still override the
    ``X-Admin-Token`` header (or clear the env var) to exercise rejection paths."""
    monkeypatch.setenv("MM_ADMIN_TOKEN", "test-admin-token")

    from starlette.testclient import TestClient

    original_init = TestClient.__init__

    def _init_with_admin(self, *args, **kwargs):
        headers = dict(kwargs.pop("headers", None) or {})
        headers.setdefault("X-Admin-Token", "test-admin-token")
        original_init(self, *args, headers=headers, **kwargs)

    monkeypatch.setattr(TestClient, "__init__", _init_with_admin)
    yield

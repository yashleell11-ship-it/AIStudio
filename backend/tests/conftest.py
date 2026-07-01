from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.models import Base
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

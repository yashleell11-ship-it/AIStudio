"""AUDIT (test-coverage shard): the suite read the developer's real database.

``SessionLocal`` was built with ``bind=get_engine()`` at import time, so the
factory captured whichever engine existed when ``database.session`` was first
imported -- the real ``backend/manhwamaniacs.db``. The autouse isolation
fixture repoints ``MM_DB_PATH`` and clears ``get_engine``'s cache, but a
factory holding the old engine never noticed, so every request whose route did
not override ``get_db`` read live developer data.

It was not theoretical: ``test_list_asurascans_series_with_sort`` was served a
real ``source_browse_cache`` row, returned ``cache.status == "fresh"``, and so
never called the connector whose arguments it exists to assert on.
"""

from __future__ import annotations

from sqlalchemy import create_engine

import database.session as dbs


def test_the_session_factory_follows_the_current_engine(tmp_path, monkeypatch):
    monkeypatch.setenv("MM_DB_PATH", str(tmp_path / "one.db"))
    dbs.get_engine.cache_clear()
    from core.config import get_settings

    get_settings.cache_clear()
    try:
        first = dbs.SessionLocal().get_bind().url

        monkeypatch.setenv("MM_DB_PATH", str(tmp_path / "two.db"))
        get_settings.cache_clear()
        dbs.get_engine.cache_clear()
        second = dbs.SessionLocal().get_bind().url

        assert first != second, (
            "SessionLocal froze one engine at import: a test that repoints "
            "MM_DB_PATH still reads the database the factory captured"
        )
        assert "two.db" in str(second)
    finally:
        get_settings.cache_clear()
        dbs.get_engine.cache_clear()


def test_an_explicit_bind_still_wins(tmp_path):
    """Callers that hand the factory an engine keep getting that engine."""
    engine = create_engine(f"sqlite:///{tmp_path / 'explicit.db'}")
    try:
        assert "explicit.db" in str(dbs.SessionLocal(bind=engine).get_bind().url)
    finally:
        engine.dispose()

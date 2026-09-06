"""AUDIT (concurrency): the image proxy holds a pooled DB connection across
the upstream fetch.

Every authenticated request resolves its session token through the request's
``get_db`` Session (``AuthService.resolve_session``, a SELECT on ``sessions``).
That SELECT checks a connection out of the engine pool and the Session keeps
it until commit/rollback/close — ``_touch`` returns without either when the
token was used <60 s ago (auth_service.py:450-458). ``get_source_page_image``
then spends up to 30 s in ``resolve_page_image`` (browse_service.py:1078,
timeout at :1155) with that connection still checked out. The cover route
already fixed this shape (``source_cache_service.get_series_cover`` rolls back
before the fetch, :420); the page-image route — the hot one, 20-200 requests
per chapter — did not.

Expected: zero pooled connections checked out while the upstream fetch runs.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import services.browse_service as browse_service
from database.models import Base, User
from database.session import get_db
from main import create_app
from services.auth_service import AuthService

pytestmark = pytest.mark.real_auth


@pytest.fixture
def pooled_engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'pool.db'}",
        connect_args={"check_same_thread": False},
        pool_size=5,
        max_overflow=5,
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, _record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def test_page_image_fetch_does_not_hold_a_pooled_connection(pooled_engine, monkeypatch):
    factory = sessionmaker(bind=pooled_engine, autoflush=False, expire_on_commit=False)
    with factory() as s:
        user = User(username="u", password_hash="x", is_admin=False, is_active=True)
        s.add(user)
        s.commit()
        token, session_row = AuthService(s).create_session(user)
        # A token used within the last minute: _touch() will NOT commit, which
        # is the steady state for every page image after the first.
        from core.time_utils import utcnow

        session_row.last_used_at = utcnow()
        s.commit()

    observed: dict[str, int] = {}

    def fake_resolve_page_image(self, source_id, page_id):  # noqa: ARG001
        observed["checked_out_during_fetch"] = pooled_engine.pool.checkedout()
        return "image/jpeg", b"\xff\xd8\xff\xd9"

    monkeypatch.setattr(browse_service.BrowseService, "resolve_page_image", fake_resolve_page_image)

    app = create_app(run_migrations=False, run_workers=False)

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        r = client.get(
            "/sources/mangadex/pages/p1/image", headers={"Authorization": f"Bearer {token}"}
        )
    assert r.status_code == 200, r.text
    assert observed["checked_out_during_fetch"] == 0, (
        f"{observed['checked_out_during_fetch']} pooled connection(s) held across the upstream fetch"
    )

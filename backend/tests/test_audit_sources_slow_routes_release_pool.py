"""AUDIT (CONC-5), the rest of the family: every slow ``/sources`` route.

``test_audit_concurrency_image_proxy_holds_pool_slot`` pins the hot one. The
same shape held for the other authenticated routes that spend up to 30 s inside
a third-party fetch: authenticating checks a pooled connection out (a SELECT on
``sessions``) and ``AuthService._touch`` deliberately neither commits nor rolls
back for a token used in the last minute, so the connection stayed checked out
for the whole upstream call. With 20+20 slots on a 2-vCPU box, one slow source
is enough to starve every other request in the process.

Each route below resolves its 18+ gate (the only DB-dependent decision it
makes) in ``get_browse_service``, before the handler body runs, so releasing
the connection first costs nothing.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import services.browse_service as browse_service
from core.time_utils import utcnow
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


# (route, the BrowseService method that performs the upstream fetch, its return)
CASES = [
    ("/sources/mangadex/series/s1", "get_series", {"id": "s1"}),
    ("/sources/mangadex/series/s1/chapters", "get_chapters", []),
    ("/sources/mangadex/series/s1/cover", "resolve_series_cover", ("image/jpeg", b"\xff\xd8\xff\xd9")),
    ("/sources/mangadex/series?query=naruto", "list_series", {"items": [], "total": 0}),
]


@pytest.mark.parametrize("path,method,payload", CASES, ids=[c[1] for c in CASES])
def test_slow_source_routes_release_the_pool_slot(
    pooled_engine, monkeypatch, path, method, payload
):
    factory = sessionmaker(bind=pooled_engine, autoflush=False, expire_on_commit=False)
    with factory() as s:
        user = User(username="u", password_hash="x", is_admin=False, is_active=True)
        s.add(user)
        s.commit()
        token, session_row = AuthService(s).create_session(user)
        # Used within the last minute, so ``_touch`` does not commit -- the
        # steady state for a reader paging through a series.
        session_row.last_used_at = utcnow()
        s.commit()

    observed: dict[str, int] = {}

    def fake_upstream(self, *args, **kwargs):  # noqa: ARG001
        observed["checked_out_during_fetch"] = pooled_engine.pool.checkedout()
        return payload

    monkeypatch.setattr(browse_service.BrowseService, method, fake_upstream)

    app = create_app(run_migrations=False, run_workers=False)

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        response = client.get(path, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200, response.text
    assert observed["checked_out_during_fetch"] == 0, (
        f"{observed['checked_out_during_fetch']} pooled connection(s) held across "
        f"the upstream fetch in {method}"
    )

"""AUDIT (concurrency): two concurrent FIRST pushes for the same chapter.

``ProgressService._apply_one`` is SELECT-then-INSERT with nothing serializing
the pair (pysqlite runs the SELECT in autocommit; the INSERT only takes the
write lock at ``flush``). Two requests for the same (user, profile, source,
series, chapter) that both observe "no row" both INSERT; the loser trips
``uq_chapter_progress`` and — with no IntegrityError handler in
``core/errors.py`` — the client gets a 500 for a push that should have merged.

Realistic trigger: the phone flushes its ``progress_outbox`` batch while the
web reader live-pushes the same chapter, or a double-fired autosave on a fresh
chapter. Expected behaviour: both pushes succeed (second merges onto the row).
"""

from __future__ import annotations

import threading

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from database.models import Base, ReadingProfile, User
from services.progress_service import ProgressInput, ProgressService


@pytest.fixture
def race_engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'race.db'}", connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, _record):  # mirror database.session
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def test_concurrent_first_pushes_for_one_chapter_both_succeed(race_engine):
    factory = sessionmaker(bind=race_engine, autoflush=False, expire_on_commit=False)
    with factory() as s:
        user = User(username="u", password_hash="x", is_admin=False, is_active=True)
        s.add(user)
        s.commit()
        prof = ReadingProfile(user_id=user.id, name="P", sort_order=0)
        s.add(prof)
        s.commit()
        uid, pid = user.id, prof.id

    payload = ProgressInput(
        source_id="mangadex", series_key="s", chapter_key="c1", last_page=3, page_count=20
    )
    both_selected = threading.Barrier(2, timeout=10)
    errors: dict[str, BaseException] = {}

    def push(name: str) -> None:
        db = factory()
        try:
            svc = ProgressService(db, user_id=uid, profile_id=pid)
            # Reproduce the interleaving: both requests run their SELECT
            # (no row yet) before either flushes its INSERT.
            original = svc._prefetch  # noqa: SLF001
            def selected_then_wait(payloads):
                rows = original(payloads)  # the SELECT: no row yet, for both
                both_selected.wait()       # ...before either flushes its INSERT
                return rows

            svc._prefetch = selected_then_wait  # noqa: SLF001
            svc.save_batch([payload])
        except BaseException as exc:  # noqa: BLE001
            errors[name] = exc
        finally:
            db.close()

    threads = [threading.Thread(target=push, args=(n,)) for n in ("A", "B")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert errors == {}, {k: repr(v)[:200] for k, v in errors.items()}

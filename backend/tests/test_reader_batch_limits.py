"""POST /reader/progress/batch is bounded and transactional (audit finding 12).

The route accepted an unbounded array and ``save_batch`` committed once per
item — N write-lock/fsync cycles on the single-writer SQLite per request. The
batch is now capped at ``PROGRESS_BATCH_MAX_ITEMS`` and applied in ONE
transaction.
"""

from __future__ import annotations

import pytest

from routes.reader import PROGRESS_BATCH_MAX_ITEMS
from services.progress_service import ProgressInput, ProgressService


@pytest.fixture
def acct(make_user, make_profile):
    user = make_user("batcher")
    profile = make_profile(user.id, "Main")
    return user.id, profile.id


@pytest.fixture
def h(as_user, acct):
    uid, pid = acct
    return as_user(uid, pid)


def _item(n: int) -> dict:
    return {
        "source_id": "mangadex",
        "series_key": "series-1",
        "chapter_key": f"ch-{n}",
        "chapter_number": float(n),
        "last_page": 3,
    }


def test_batch_over_cap_is_rejected_with_413(client, h):
    body = [_item(n) for n in range(PROGRESS_BATCH_MAX_ITEMS + 1)]
    response = client.post("/reader/progress/batch", json=body, headers=h)
    assert response.status_code == 413
    payload = response.json()
    assert payload["code"] == "batch_too_large"
    assert payload["details"]["max_items"] == PROGRESS_BATCH_MAX_ITEMS


def test_batch_at_cap_is_accepted(client, h):
    body = [_item(n) for n in range(PROGRESS_BATCH_MAX_ITEMS)]
    response = client.post("/reader/progress/batch", json=body, headers=h)
    assert response.status_code == 200, response.text
    assert response.json()["saved"] == PROGRESS_BATCH_MAX_ITEMS


def test_save_batch_commits_exactly_once(db_session, acct, monkeypatch):
    uid, pid = acct
    service = ProgressService(db_session, user_id=uid, profile_id=pid)

    commits = {"n": 0}
    real_commit = db_session.commit

    def counting_commit():
        commits["n"] += 1
        real_commit()

    monkeypatch.setattr(db_session, "commit", counting_commit)

    payloads = [
        ProgressInput(
            source_id="mangadex",
            series_key="series-1",
            chapter_key=f"ch-{n}",
            chapter_number=float(n),
            last_page=5,
        )
        for n in range(10)
    ]
    result = service.save_batch(payloads)

    assert result["saved"] == 10
    assert commits["n"] == 1  # one transaction for the whole batch


def test_batch_merge_semantics_survive_the_single_transaction(db_session, acct):
    """Two pushes for the SAME chapter in one batch: the second must see the
    first's pending row (furthest-wins, no duplicate insert)."""
    uid, pid = acct
    service = ProgressService(db_session, user_id=uid, profile_id=pid)

    result = service.save_batch(
        [
            ProgressInput(
                source_id="mangadex",
                series_key="series-1",
                chapter_key="ch-1",
                chapter_number=1.0,
                last_page=5,
            ),
            ProgressInput(
                source_id="mangadex",
                series_key="series-1",
                chapter_key="ch-1",
                chapter_number=1.0,
                last_page=2,  # behind: must not rewind
            ),
        ]
    )
    assert result["saved"] == 2
    items = service.get_series_progress("mangadex", "series-1")
    assert len(items) == 1
    assert items[0]["last_page"] == 5

"""Sweep guardrails and the follow cap (audit finding 14).

The full sweep walked every followed row with no per-source HTTP budget and
no whole-run deadline, and follows themselves were uncapped — so one profile
could turn every scheduled pass into an hours-long sequential network job.
"""

from __future__ import annotations

import pytest

from core.config import get_settings
from services import update_service
from services.update_service import UpdateService


@pytest.fixture
def acct(make_user, make_profile):
    user = make_user("sweeper")
    profile = make_profile(user.id, "Main")
    return user.id, profile.id


@pytest.fixture
def _env(monkeypatch):
    """Small, deterministic guardrails for these tests."""
    monkeypatch.setenv("MM_UPDATE_SWEEP_SOURCE_BUDGET_SECONDS", "100")
    monkeypatch.setenv("MM_UPDATE_SWEEP_DEADLINE_MINUTES", "10")  # 600s
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch):
    fake = _FakeClock()
    monkeypatch.setattr(update_service, "_monotonic", fake)
    return fake


def _stub_check_one(monkeypatch, clock, *, cost_by_source: dict[str, float]):
    """Each _check_one advances the fake clock by its source's cost."""
    checked: list[str] = []

    def fake_check_one(self, row):  # noqa: ARG001
        clock.now += cost_by_source.get(row.source_id, 1.0)
        checked.append(f"{row.source_id}/{row.series_key}")
        return 0

    monkeypatch.setattr(UpdateService, "_check_one", fake_check_one)
    return checked


def test_wedged_source_burns_its_budget_and_its_remaining_rows_are_skipped(
    db_session, acct, seed_follow, _env, clock, monkeypatch
):
    uid, pid = acct
    # Three rows on the wedged source, one on a healthy source, ordered so the
    # wedged rows come first.
    seed_follow(uid, pid, source_id="deadsource", series_key="a")
    seed_follow(uid, pid, source_id="deadsource", series_key="b")
    seed_follow(uid, pid, source_id="deadsource", series_key="c")
    seed_follow(uid, pid, source_id="mangadex", series_key="d")

    checked = _stub_check_one(
        monkeypatch, clock, cost_by_source={"deadsource": 90.0, "mangadex": 1.0}
    )

    result = UpdateService(db_session, system=True).run_check(trigger="scheduled")

    # deadsource row 1 (90s) + row 2 (crosses the 100s budget) — row 3 skipped.
    assert "deadsource/a" in checked
    assert "deadsource/b" in checked
    assert "deadsource/c" not in checked
    # The healthy source is unaffected by the wedged one's spent budget.
    assert "mangadex/d" in checked
    assert result["series_checked"] == 3
    assert result["status"] == "completed"


def test_sweep_deadline_stops_the_pass_and_reports_it(
    db_session, acct, seed_follow, _env, clock, monkeypatch
):
    uid, pid = acct
    for n in range(4):
        seed_follow(uid, pid, source_id=f"src{n}", series_key=f"s{n}")

    # Every check costs 250s: rows 1-3 fit before the 600s deadline trips.
    checked = _stub_check_one(
        monkeypatch,
        clock,
        cost_by_source={f"src{n}": 250.0 for n in range(4)},
    )

    result = UpdateService(db_session, system=True).run_check(trigger="scheduled")

    assert len(checked) == 3
    assert result["series_checked"] == 3
    assert result["status"] == "completed"
    assert "deadline" in (result["error"] or "")


def test_guards_disabled_at_zero_check_everything(
    db_session, acct, seed_follow, clock, monkeypatch
):
    monkeypatch.setenv("MM_UPDATE_SWEEP_SOURCE_BUDGET_SECONDS", "0")
    monkeypatch.setenv("MM_UPDATE_SWEEP_DEADLINE_MINUTES", "0")
    get_settings.cache_clear()
    try:
        uid, pid = acct
        for n in range(3):
            seed_follow(uid, pid, source_id="onesource", series_key=f"s{n}")
        checked = _stub_check_one(
            monkeypatch, clock, cost_by_source={"onesource": 10_000.0}
        )
        result = UpdateService(db_session, system=True).run_check(trigger="manual")
        assert len(checked) == 3
        assert result["error"] is None
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# The follow cap
# ---------------------------------------------------------------------------


def test_follow_cap_rejects_beyond_the_limit(client, as_user, acct, monkeypatch):
    from services.browse_service import get_browse_service
    from tests._fakes import FakeBrowse

    monkeypatch.setenv("MM_MAX_FOLLOWS_PER_PROFILE", "2")
    get_settings.cache_clear()
    uid, pid = acct
    h = as_user(uid, pid)
    client.app.dependency_overrides[get_browse_service] = lambda: FakeBrowse()
    try:
        for n in range(2):
            response = client.post(
                "/library/follow",
                json={"source_id": "mangadex", "series_key": f"series-{n}"},
                headers=h,
            )
            assert response.status_code == 200, response.text

        over = client.post(
            "/library/follow",
            json={"source_id": "mangadex", "series_key": "series-over"},
            headers=h,
        )
        assert over.status_code == 400
        assert over.json()["code"] == "follow_limit_reached"

        # Re-following an existing series is idempotent, not a new follow —
        # it must not trip the cap.
        again = client.post(
            "/library/follow",
            json={"source_id": "mangadex", "series_key": "series-0"},
            headers=h,
        )
        assert again.status_code == 200, again.text
    finally:
        client.app.dependency_overrides.pop(get_browse_service, None)
        get_settings.cache_clear()

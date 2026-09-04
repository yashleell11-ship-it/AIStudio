"""Dead connectors, made visible and harmless.

Roughly 100 of the ~151 installed connectors are dead and nothing recorded it:
the owner learned a source had died only when a followed series quietly stopped
updating. These tests pin the four properties that fix costs nothing unless they
hold -- failures are recorded, a recovery clears the streak, a long streak
demotes (and un-demotes) the source in search ordering, and none of it leaks a
mature source's existence past the 18+ gate.

The write policy is tested as hard as the behaviour: this database is SQLite
with a single writer that page reads already contend for, so "search records
health" must not mean "every search writes 151 rows".
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import sessionmaker

from core.config import get_settings
from core.time_utils import utcnow
from database.models import SourceHealth
from database.session import get_db
from main import create_app
from services import source_health
from services.source_health import (
    DEAD_AFTER_FAILURES,
    DEMOTE_AFTER_FAILURES,
    MAX_STREAK,
    REFRESH_INTERVAL,
    record_outcomes,
)
from tests.test_sources_search import (
    _FakeConnector,
    _FakeDescriptor,
    _group,
    _make_list_installed,
    _search,
    _series,
)

# Real registry entries, as in test_mature_gate_per_profile: nhentai is flagged
# MATURE, mangadex is not. The gate has to hold against the connectors actually
# installed, and nothing below touches the network.
MATURE_SOURCE = "nhentai"
SAFE_SOURCE = "mangadex"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def session_factory(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, autocommit=False)


@pytest.fixture
def client(db_engine, session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app = create_app(run_migrations=False, run_workers=False)
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


def _health_rows(session_factory) -> dict[str, SourceHealth]:
    db = session_factory()
    try:
        return {row.source_id: row for row in db.execute(select(SourceHealth)).scalars()}
    finally:
        db.close()


def _seed_health(session_factory, source_id: str, **values) -> None:
    db = session_factory()
    try:
        db.add(SourceHealth(source_id=source_id, **values))
        db.commit()
    finally:
        db.close()


@contextmanager
def _count_health_writes(engine):
    """Count INSERT/UPDATE statements hitting ``source_health``.

    Statement-level rather than commit-level: the point of the write policy is
    that a steady-state search issues no write at all, and a commit count would
    hide 151 UPDATEs behind one commit.
    """
    counter = {"writes": 0}

    def _hook(conn, cursor, statement, parameters, context, executemany):
        normalized = " ".join(statement.split()).upper()
        if not normalized.startswith(
            ("INSERT INTO SOURCE_HEALTH", "UPDATE SOURCE_HEALTH")
        ):
            return
        # One statement is one row unless the driver was handed several
        # parameter *sets* (a sequence of sequences) to execute in a batch.
        if executemany and parameters and isinstance(parameters[0], (list, tuple, dict)):
            counter["writes"] += len(parameters)
        else:
            counter["writes"] += 1

    event.listen(engine, "before_cursor_execute", _hook)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", _hook)


# ---------------------------------------------------------------------------
# Recording: failures, recovery, and the streak
# ---------------------------------------------------------------------------


def test_a_failing_source_is_recorded(client, session_factory):
    descriptors = [_FakeDescriptor("good"), _FakeDescriptor("bad")]
    connectors = {
        "good": _FakeConnector([_series("g-1", "Good Hit")]),
        "bad": _FakeConnector([], raises=RuntimeError("cloudflare wall")),
    }

    payload = _search(client, descriptors, connectors, "hit").json()

    rows = _health_rows(session_factory)
    assert rows["bad"].consecutive_failures == 1
    assert "cloudflare wall" in rows["bad"].last_error
    assert rows["bad"].last_error_at is not None
    assert rows["bad"].last_ok_at is None
    # ...and the source that answered is recorded as healthy, not just "not
    # failing" -- an absent row would be indistinguishable from never probed.
    assert rows["good"].consecutive_failures == 0
    assert rows["good"].last_ok_at is not None

    assert _group(payload, "bad")["health"]["status"] == "failing"
    assert _group(payload, "good")["health"]["status"] == "ok"


def test_an_empty_answer_is_health_not_failure(client, session_factory):
    """A source that answers "no results" is reachable. Counting that as an
    outage would demote working sources for narrow queries."""
    descriptors = [_FakeDescriptor("quiet")]
    connectors = {"quiet": _FakeConnector([])}

    payload = _search(client, descriptors, connectors, "zzz-no-such-title").json()

    assert _health_rows(session_factory)["quiet"].consecutive_failures == 0
    assert _group(payload, "quiet")["health"]["status"] == "ok"


def test_a_source_that_ignored_the_query_is_not_marked_unhealthy(
    client, session_factory
):
    """The catalog-dump case (baozimh) is a relevance problem, not an outage.
    Marking it dead would demote a reachable source and make the health table
    lie about why its results were dropped."""
    descriptors = [_FakeDescriptor("baozimh")]
    catalog = [_series(f"bz-{i}", f"斗罗大陆 {i}") for i in range(20)]
    connectors = {"baozimh": _FakeConnector(catalog)}

    payload = _search(client, descriptors, connectors, "lookism").json()

    group = _group(payload, "baozimh")
    assert "unrelated" in group["error"]  # results still dropped
    assert group["health"]["status"] == "ok"
    assert _health_rows(session_factory)["baozimh"].consecutive_failures == 0


def test_unprobed_sources_report_unknown_not_ok(client):
    """An empty query probes nothing, so nothing is learned -- and a source
    nobody has checked must not look healthy. That false "fine" is exactly how
    ~100 dead connectors stayed invisible."""
    descriptors = [_FakeDescriptor("never-checked")]

    with patch(
        "services.browse_service.list_installed_connectors",
        _make_list_installed(descriptors),
    ), patch(
        "services.browse_service.create_connector",
        side_effect=AssertionError("should not query connectors on empty query"),
    ):
        payload = client.get("/sources/search", params={"q": "  "}).json()

    assert _group(payload, "never-checked")["health"]["status"] == "unknown"
    assert _group(payload, "never-checked")["health"]["demoted"] is False


def test_repeated_failures_climb_to_demotion_then_dead(client, session_factory):
    descriptors = [_FakeDescriptor("bad")]
    connectors = {"bad": _FakeConnector([], raises=RuntimeError("boom"))}

    seen = []
    for _ in range(DEAD_AFTER_FAILURES + 3):
        payload = _search(client, descriptors, connectors, "hit").json()
        seen.append(_group(payload, "bad")["health"])

    # Not demoted before the threshold, demoted from it onward.
    assert [h["demoted"] for h in seen[: DEMOTE_AFTER_FAILURES - 1]] == [False] * (
        DEMOTE_AFTER_FAILURES - 1
    )
    assert seen[DEMOTE_AFTER_FAILURES - 1]["demoted"] is True
    assert seen[DEMOTE_AFTER_FAILURES - 1]["status"] == "failing"
    assert seen[DEAD_AFTER_FAILURES - 1]["status"] == "dead"
    # The streak saturates instead of counting forever: past the last threshold
    # the number changes no decision, and incrementing it would cost a write per
    # dead source per search.
    assert seen[-1]["consecutive_failures"] == MAX_STREAK
    assert _health_rows(session_factory)["bad"].consecutive_failures == MAX_STREAK


def test_recovery_clears_the_streak(client, session_factory):
    """One success is enough. A source that comes back must come back on its
    own -- no operator action, no cooldown."""
    descriptors = [_FakeDescriptor("flaky")]
    dead = {"flaky": _FakeConnector([], raises=RuntimeError("boom"))}
    alive = {"flaky": _FakeConnector([_series("f-1", "Hit")])}

    for _ in range(DEAD_AFTER_FAILURES):
        _search(client, descriptors, dead, "hit")
    assert _health_rows(session_factory)["flaky"].consecutive_failures == MAX_STREAK

    payload = _search(client, descriptors, alive, "hit").json()

    row = _health_rows(session_factory)["flaky"]
    assert row.consecutive_failures == 0
    assert row.last_ok_at is not None
    # The failure evidence is kept: the owner still needs to see it went down
    # and why, not just that it is up now.
    assert row.last_error_at is not None
    assert row.last_error == "boom"
    health = _group(payload, "flaky")["health"]
    assert health["status"] == "ok"
    assert health["demoted"] is False


# ---------------------------------------------------------------------------
# Demotion in search ordering -- applied, visible, and reversible
# ---------------------------------------------------------------------------


def _fail_until_demoted(client, source_id: str, name: str) -> None:
    descriptors = [_FakeDescriptor(source_id, name=name)]
    connectors = {source_id: _FakeConnector([], raises=RuntimeError("boom"))}
    for _ in range(DEMOTE_AFTER_FAILURES):
        _search(client, descriptors, connectors, "hit")


def test_a_demoted_source_sinks_below_the_ones_still_answering(
    client, session_factory
):
    """"aaa-dead" sorts first by display name and would otherwise sit above a
    working source that returned nothing this round."""
    _fail_until_demoted(client, "aaa-dead", "AAA Dead")

    descriptors = [
        _FakeDescriptor("aaa-dead", name="AAA Dead"),
        _FakeDescriptor("zzz-live", name="ZZZ Live"),
    ]
    connectors = {
        "aaa-dead": _FakeConnector([], raises=RuntimeError("boom")),
        "zzz-live": _FakeConnector([]),  # answers, no results
    }

    payload = _search(client, descriptors, connectors, "hit").json()

    assert [g["source"] for g in payload["groups"]] == [None, "zzz-live", "aaa-dead"]
    assert payload["sources_demoted"] == 1


def test_a_demoted_source_is_flagged_never_hidden(client, session_factory):
    """Sinking it is the whole intervention. If it vanished, the owner would be
    back to not knowing a source died."""
    _fail_until_demoted(client, "dead", "Dead Source")

    descriptors = [_FakeDescriptor("dead", name="Dead Source")]
    connectors = {"dead": _FakeConnector([], raises=RuntimeError("still down"))}

    payload = _search(client, descriptors, connectors, "hit").json()

    group = _group(payload, "dead")
    assert group is not None
    assert group["status"] == "error"
    assert "still down" in group["error"]
    assert group["health"]["demoted"] is True
    assert group["health"]["consecutive_failures"] >= DEMOTE_AFTER_FAILURES
    assert group["health"]["last_error"] is not None
    # It is also still in the source listing, flagged.
    listed = {s["id"]: s for s in client.get("/sources").json()}
    assert listed  # sanity: the real registry answered
    health_listing = {s["id"]: s for s in client.get("/sources/health").json()}
    assert set(listed) == set(health_listing)


def test_demotion_is_reversed_by_a_single_success(client, session_factory):
    """The demotion must not be a one-way door: a recovered source is restored
    by the very search that finds it working, in that same response."""
    _fail_until_demoted(client, "aaa-dead", "AAA Dead")

    descriptors = [
        _FakeDescriptor("aaa-dead", name="AAA Dead"),
        _FakeDescriptor("zzz-live", name="ZZZ Live"),
    ]
    demoted_first = _search(
        client,
        descriptors,
        {
            "aaa-dead": _FakeConnector([], raises=RuntimeError("boom")),
            "zzz-live": _FakeConnector([]),
        },
        "hit",
    ).json()
    assert [g["source"] for g in demoted_first["groups"]][-1] == "aaa-dead"

    recovered = _search(
        client,
        descriptors,
        {
            "aaa-dead": _FakeConnector([_series("a-1", "Hit")]),
            "zzz-live": _FakeConnector([]),
        },
        "hit",
    ).json()

    assert _group(recovered, "aaa-dead")["health"]["demoted"] is False
    # Back on top: it has the only relevant hit again.
    assert [g["source"] for g in recovered["groups"]] == [None, "aaa-dead", "zzz-live"]
    assert recovered["sources_demoted"] == 0


# ---------------------------------------------------------------------------
# Write policy: no write on the hot path
# ---------------------------------------------------------------------------


def test_a_steady_state_search_writes_nothing(client, session_factory, db_engine):
    """The first search records what it learned; identical searches after it
    must not touch the database again. Writing per source per search would mean
    ~151 UPDATEs on every search against a single-writer SQLite."""
    descriptors = [_FakeDescriptor("good"), _FakeDescriptor("bad")]
    connectors = {
        "good": _FakeConnector([_series("g-1", "Hit")]),
        "bad": _FakeConnector([], raises=RuntimeError("boom")),
    }

    with _count_health_writes(db_engine) as first:
        _search(client, descriptors, connectors, "hit")
    assert first["writes"] == 2  # first observation of each source

    # "bad" keeps climbing towards the thresholds, so it keeps writing; "good"
    # has nothing new to say and must go quiet.
    with _count_health_writes(db_engine) as second:
        _search(client, descriptors, connectors, "hit")
    assert second["writes"] == 1

    # Once the streak saturates, even the failing source stops writing.
    for _ in range(DEAD_AFTER_FAILURES):
        _search(client, descriptors, connectors, "hit")
    with _count_health_writes(db_engine) as steady:
        _search(client, descriptors, connectors, "hit")
        _search(client, descriptors, connectors, "hit")
    assert steady["writes"] == 0


def test_a_state_change_still_writes(client, session_factory, db_engine):
    """The saving is only legitimate if the transitions survive it."""
    descriptors = [_FakeDescriptor("s")]
    ok = {"s": _FakeConnector([_series("s-1", "Hit")])}
    down = {"s": _FakeConnector([], raises=RuntimeError("boom"))}

    _search(client, descriptors, ok, "hit")
    with _count_health_writes(db_engine) as failed:
        _search(client, descriptors, down, "hit")  # ok -> failing
    assert failed["writes"] == 1

    with _count_health_writes(db_engine) as recovered:
        _search(client, descriptors, ok, "hit")  # failing -> ok
    assert recovered["writes"] == 1


def test_an_unchanged_row_is_refreshed_once_the_interval_lapses(db_session):
    """Suppressing no-op writes would otherwise freeze ``last_checked_at`` at
    the last state change, so a source probed a minute ago would read "checked
    three weeks ago"."""
    first = utcnow() - REFRESH_INTERVAL - timedelta(minutes=1)
    record_outcomes(db_session, {"s": None}, now=first)
    assert db_session.execute(select(SourceHealth)).scalar_one().last_checked_at == first

    # Well inside the interval: nothing changed, nothing written.
    soon = first + timedelta(minutes=5)
    record_outcomes(db_session, {"s": None}, now=soon)
    assert db_session.execute(select(SourceHealth)).scalar_one().last_checked_at == first

    later = first + REFRESH_INTERVAL
    record_outcomes(db_session, {"s": None}, now=later)
    row = db_session.execute(select(SourceHealth)).scalar_one()
    assert row.last_checked_at == later
    assert row.last_ok_at == later


def test_error_text_is_truncated(db_session):
    """A connector can raise with a whole Cloudflare interstitial attached."""
    record_outcomes(db_session, {"s": "x" * 5000})
    row = db_session.execute(select(SourceHealth)).scalar_one()
    assert len(row.last_error) == source_health.ERROR_MAX_CHARS


def test_recording_never_breaks_a_search(client, session_factory):
    """Health is diagnostic metadata about the search. A failure to record it
    must not turn a working search into a 500 -- the owner would lose the
    feature that works to save the one that reports on it."""
    _seed_health(session_factory, "good", consecutive_failures=2, last_error="earlier")
    descriptors = [_FakeDescriptor("good")]
    connectors = {"good": _FakeConnector([_series("g-1", "Hit")])}

    with patch(
        "services.browse_service.record_outcomes",
        side_effect=RuntimeError("health table exploded"),
    ):
        response = _search(client, descriptors, connectors, "hit")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["title"] == "Hit"
    # Falls back to the last known health rather than inventing one.
    assert _group(payload, "good")["health"]["consecutive_failures"] == 2


# ---------------------------------------------------------------------------
# Exposure
# ---------------------------------------------------------------------------


def test_health_endpoint_lists_every_source_worst_first(client, session_factory):
    now = utcnow()
    _seed_health(
        session_factory,
        SAFE_SOURCE,
        consecutive_failures=DEAD_AFTER_FAILURES,
        last_error="gone",
        last_error_at=now,
        last_checked_at=now,
    )

    response = client.get("/sources/health")

    assert response.status_code == 200
    items = response.json()
    assert response.headers["X-Total-Count"] == str(len(items))
    assert items[0]["id"] == SAFE_SOURCE
    assert items[0]["health"]["status"] == "dead"
    assert items[0]["health"]["demoted"] is True
    assert items[0]["health"]["last_error"] == "gone"
    # Never-probed sources are reported as unknown, and sort after the dead one
    # but ahead of nothing else here (nothing is healthy yet).
    assert all(i["health"]["status"] == "unknown" for i in items[1:])
    # Same shape as GET /sources, so one client component renders both.
    assert set(items[0]) == set(client.get("/sources").json()[0])


def test_source_listing_carries_health(client, session_factory):
    _seed_health(
        session_factory, SAFE_SOURCE, consecutive_failures=4, last_error="down"
    )

    listed = {s["id"]: s for s in client.get("/sources").json()}

    assert listed[SAFE_SOURCE]["health"]["consecutive_failures"] == 4
    assert listed[SAFE_SOURCE]["health"]["demoted"] is True


def test_summary_counts_by_status(client, session_factory):
    _seed_health(session_factory, SAFE_SOURCE, consecutive_failures=DEAD_AFTER_FAILURES)

    summary = client.get("/system/source-health").json()

    assert summary["dead"] == 1
    assert summary["demoted"] == 1
    assert summary["total"] == len(client.get("/sources").json())
    assert summary["unknown"] == summary["total"] - 1


# ---------------------------------------------------------------------------
# The 18+ gate: health is global, the source list is not
# ---------------------------------------------------------------------------


def _set_gate(client, profile_id: int, enabled: bool) -> None:
    response = client.put(
        "/settings",
        json={"mature_content_enabled": enabled},
        headers={"X-Profile-Id": str(profile_id)},
    )
    assert response.status_code == 200, response.text


@pytest.mark.real_auth
class TestMatureGateHoldsForHealth:
    """A mature source's health must not leak to a profile that cannot see the
    source. Health is stored globally (a site being down is a property of the
    site), so the gate has to hold at read time, on every surface that exposes
    it."""

    @pytest.fixture
    def env(self, db_engine, monkeypatch, tmp_path):
        monkeypatch.setattr("core.config.SETTINGS_PATH", tmp_path / "settings.json")
        monkeypatch.setenv("MM_COOKIE_SECURE", "false")
        get_settings.cache_clear()

        factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)

        def override_get_db():
            db = factory()
            try:
                yield db
            finally:
                db.close()

        app = create_app(run_migrations=False, run_workers=False)
        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        reg = client.post(
            "/auth/register", json={"username": "owner", "password": "supersecret"}
        )
        assert reg.status_code in (200, 201), reg.text
        off = client.post("/profiles", json={"name": "action"}).json()
        on = client.post("/profiles", json={"name": "porn"}).json()
        _set_gate(client, on["id"], True)

        # Both sources have recorded health; only one of them is adult.
        now = utcnow()
        db = factory()
        try:
            db.add_all(
                [
                    SourceHealth(
                        source_id=MATURE_SOURCE,
                        consecutive_failures=DEAD_AFTER_FAILURES,
                        last_error="adult source is down",
                        last_error_at=now,
                        last_checked_at=now,
                    ),
                    SourceHealth(
                        source_id=SAFE_SOURCE,
                        consecutive_failures=DEMOTE_AFTER_FAILURES,
                        last_error="safe source is down",
                        last_error_at=now,
                        last_checked_at=now,
                    ),
                ]
            )
            db.commit()
        finally:
            db.close()

        yield {"client": client, "off": off["id"], "on": on["id"]}
        get_settings.cache_clear()

    def test_health_listing_is_gated(self, env):
        client = env["client"]
        off = {
            item["id"]: item
            for item in client.get(
                "/sources/health", headers={"X-Profile-Id": str(env["off"])}
            ).json()
        }
        on = {
            item["id"]: item
            for item in client.get(
                "/sources/health", headers={"X-Profile-Id": str(env["on"])}
            ).json()
        }

        assert MATURE_SOURCE not in off
        assert MATURE_SOURCE in on
        assert on[MATURE_SOURCE]["health"]["last_error"] == "adult source is down"
        # Positive control: the gated profile does see the non-adult source's
        # health, so the assertion above is not passing on a broken endpoint.
        assert off[SAFE_SOURCE]["health"]["last_error"] == "safe source is down"

    def test_source_listing_health_is_gated(self, env):
        client = env["client"]
        off = {
            item["id"] for item in client.get(
                "/sources", headers={"X-Profile-Id": str(env["off"])}
            ).json()
        }
        assert MATURE_SOURCE not in off
        assert SAFE_SOURCE in off

    def test_summary_does_not_count_hidden_sources(self, env):
        """The counts are per-caller too: a total that included adult sources
        would let the gated profile work out how many exist."""
        client = env["client"]
        off = client.get(
            "/system/source-health", headers={"X-Profile-Id": str(env["off"])}
        ).json()
        on = client.get(
            "/system/source-health", headers={"X-Profile-Id": str(env["on"])}
        ).json()

        assert off["total"] < on["total"]
        # The adult source is dead; that must not show up in the gated tally.
        assert off["dead"] == 0
        assert on["dead"] == 1
        assert off["failing"] == 1 and on["failing"] == 1

    def test_search_groups_do_not_carry_hidden_health(self, env):
        client = env["client"]
        payload = client.get(
            "/sources/search",
            params={"q": ""},
            headers={"X-Profile-Id": str(env["off"])},
        ).json()

        assert MATURE_SOURCE not in {g["source"] for g in payload["groups"]}


def test_a_search_query_never_reaches_the_global_health_row():
    """The health table is global, so an error string carrying the failing
    request URL leaked one account's search terms to every other account."""
    from services.browse_service import _search_error_message

    leaky = RuntimeError(
        "Client error '404 Not Found' for url "
        "'https://example.test/search?q=my+very+private+search'"
    )
    message = _search_error_message(leaky)

    assert "private" not in message
    assert "example.test" not in message
    assert "http" not in message
    # ...while still saying what went wrong.
    assert "404" in message

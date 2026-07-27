"""The 18+ gate, resolved per (user, profile) and honoured everywhere.

The bug these guard: the gate lived in two unconnected places. The clients wrote
``ReadingProfile.mature_content_enabled`` (via PUT /settings with X-Profile-Id)
while the browse layer read the global ``Settings.mature_content_enabled``, so
flipping the switch in the app changed the value the app read back and nothing
else -- an adult source stayed listed and browsable, and an adult series the
profile already had stayed in the grid, in search, and in the statistics.

Driven through the real HTTP stack with real auth and two real profiles, because
the whole point is the interaction between the header, the profile row, and the
read paths. Three things are asserted for every surface:

* invisible while the active profile has 18+ off,
* visible again once that profile turns it on, and
* profile A's setting has no effect on profile B.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from core.config import get_settings, update_persisted_settings
from database.models import (
    Chapter,
    Library,
    Page,
    ReadingProgress,
    Series,
    SeriesTracker,
    UserSeriesState,
)
from database.session import get_db
from main import create_app

# Real registry entries: toonily is flagged MATURE, mangadex is not. Using the
# real registry (rather than descriptor doubles) is deliberate here -- the gate
# has to hold against the connectors actually installed, and none of the
# endpoints exercised below touch the network.
MATURE_SOURCE = "toonily"
SAFE_SOURCE = "mangadex"


def _make_client(db_engine):
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app = create_app(run_migrations=False, run_workers=False)
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), factory


def _seed_library(factory, *, user_id: int, profile_ids: list[int]) -> dict[str, int]:
    """One safe and one adult series, both in BOTH profiles' libraries.

    Membership is held constant on purpose so the gate is the only variable
    between the two profiles.
    """
    db = factory()
    try:
        lib = Library(name="Main", root_path="/lib")
        db.add(lib)
        db.flush()
        safe = Series(
            library_id=lib.id,
            title="Wholesome Adventure",
            folder_path="/lib/safe",
            sort_title="wholesome adventure",
            content_rating="safe",
        )
        adult = Series(
            library_id=lib.id,
            title="Adults Only",
            folder_path="/lib/adult",
            sort_title="adults only",
            content_rating="pornographic",
        )
        db.add_all([safe, adult])
        db.flush()
        db.add_all(
            UserSeriesState(
                user_id=user_id,
                profile_id=profile_id,
                series_id=series.id,
                in_library=True,
            )
            for profile_id in profile_ids
            for series in (safe, adult)
        )
        chapters = {}
        for series in (safe, adult):
            chapter = Chapter(
                series_id=series.id,
                title="Ch1",
                number=1.0,
                page_count=1,
                sort_key="0001",
            )
            db.add(chapter)
            db.flush()
            db.add(Page(chapter_id=chapter.id, number=1, file_path="/lib/x/1.jpg"))
            chapters[series.id] = chapter.id
        # Both profiles have read into both series, so Continue Reading has an
        # adult entry to hide.
        for profile_id in profile_ids:
            for series in (safe, adult):
                db.add(
                    ReadingProgress(
                        user_id=user_id,
                        profile_id=profile_id,
                        series_id=series.id,
                        chapter_id=chapters[series.id],
                        last_page=1,
                        progress_pct=50.0,
                    )
                )
        db.commit()
        return {
            "safe": safe.id,
            "adult": adult.id,
            "safe_chapter": chapters[safe.id],
            "adult_chapter": chapters[adult.id],
        }
    finally:
        db.close()


def _set_gate(client, profile_id: int, enabled: bool) -> None:
    response = client.put(
        "/settings",
        json={"mature_content_enabled": enabled},
        headers={"X-Profile-Id": str(profile_id)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["mature_content_enabled"] is enabled


@pytest.mark.real_auth
class TestMatureGatePerProfile:
    @pytest.fixture
    def env(self, db_engine, monkeypatch, tmp_path):
        # Isolate config/settings.json so the global fallback is a throwaway
        # file and the real one is never written.
        monkeypatch.setattr("core.config.SETTINGS_PATH", tmp_path / "settings.json")
        monkeypatch.setenv("MM_COOKIE_SECURE", "false")
        get_settings.cache_clear()

        client, factory = _make_client(db_engine)
        reg = client.post(
            "/auth/register", json={"username": "owner", "password": "supersecret"}
        )
        assert reg.status_code in (200, 201), reg.text
        owner_id = reg.json()["user"]["id"]
        action = client.post("/profiles", json={"name": "action"}).json()
        porn = client.post("/profiles", json={"name": "porn"}).json()

        ids = _seed_library(
            factory, user_id=owner_id, profile_ids=[action["id"], porn["id"]]
        )
        # "action" keeps 18+ off (the default); "porn" opts in.
        _set_gate(client, porn["id"], True)

        yield {
            "client": client,
            "factory": factory,
            "owner_id": owner_id,
            "off": action["id"],
            "on": porn["id"],
            **ids,
        }
        get_settings.cache_clear()

    # -- by-id reachability (the gate must not be one numeric id away) -----

    def test_hidden_series_is_not_reachable_by_id(self, env):
        """404 on every by-id surface, not just the grid.

        A gate that hides a series from listings while its cover and pages stay
        fetchable by id is not a gate. The cover matters most: it is the single
        most identifying artefact of an adult series.
        """
        client = env["client"]
        off = {"X-Profile-Id": str(env["off"])}
        on = {"X-Profile-Id": str(env["on"])}

        for path in (
            f"/library/series/{env['adult']}",
            f"/library/covers/{env['adult']}",
            f"/library/chapters/{env['adult_chapter']}",
            f"/reader/chapter/{env['adult_chapter']}",
        ):
            assert client.get(path, headers=off).status_code == 404, path

        # Positive control, so the assertions above cannot pass merely because
        # the route is broken for everyone. The cover is excluded: this fixture
        # seeds no cover file, so that route 404s for its own reason and proves
        # nothing either way.
        for path in (
            f"/library/series/{env['adult']}",
            f"/library/chapters/{env['adult_chapter']}",
            f"/reader/chapter/{env['adult_chapter']}",
        ):
            assert client.get(path, headers=on).status_code == 200, path

    def test_safe_series_stays_reachable_by_id_while_gated(self, env):
        """The gate must not become a blanket denial of by-id access."""
        client = env["client"]
        off = {"X-Profile-Id": str(env["off"])}
        assert client.get(f"/library/series/{env['safe']}", headers=off).status_code == 200
        assert client.get(f"/reader/chapter/{env['safe_chapter']}", headers=off).status_code == 200

    # -- tag names ---------------------------------------------------------

    def test_a_tag_only_on_a_hidden_series_is_not_named(self, env):
        """Statistics stopped counting the tag; the tag list kept naming it."""
        client = env["client"]
        off = {"X-Profile-Id": str(env["off"])}
        on = {"X-Profile-Id": str(env["on"])}

        adult_tag = client.post(
            "/library/tags", json={"name": "hentai-only"}, headers=on
        ).json()
        client.post(
            f"/library/series/{env['adult']}/tags",
            json={"tag_id": adult_tag["id"]},
            headers=on,
        )

        assert "hentai-only" not in {t["name"] for t in client.get("/library/tags", headers=off).json()}
        assert "hentai-only" in {t["name"] for t in client.get("/library/tags", headers=on).json()}

    def test_an_unapplied_tag_is_still_listed(self, env):
        """A freshly created label has no series yet -- hiding it would make tag
        creation look broken, which is a different bug from the leak above."""
        client = env["client"]
        off = {"X-Profile-Id": str(env["off"])}
        client.post("/library/tags", json={"name": "to-read"}, headers=off)
        assert "to-read" in {t["name"] for t in client.get("/library/tags", headers=off).json()}

    # -- sources -----------------------------------------------------------

    def test_mature_source_is_listed_only_for_the_profile_that_opted_in(self, env):
        client = env["client"]
        off = {s["id"] for s in client.get("/sources", headers={"X-Profile-Id": str(env["off"])}).json()}
        on = {s["id"] for s in client.get("/sources", headers={"X-Profile-Id": str(env["on"])}).json()}

        assert MATURE_SOURCE not in off
        assert MATURE_SOURCE in on
        # A non-adult source is unaffected by either profile's setting.
        assert SAFE_SOURCE in off and SAFE_SOURCE in on

    def test_mature_source_browse_is_404_for_the_gated_profile(self, env):
        """Not-found rather than forbidden: a 403 would confirm the source
        exists, which is itself the disclosure the gate is meant to prevent."""
        client = env["client"]
        blocked = client.get(
            f"/sources/{MATURE_SOURCE}/browse-modes",
            headers={"X-Profile-Id": str(env["off"])},
        )
        assert blocked.status_code == 404
        assert blocked.json()["code"] == "source_not_found"

        allowed = client.get(
            f"/sources/{MATURE_SOURCE}/browse-modes",
            headers={"X-Profile-Id": str(env["on"])},
        )
        assert allowed.status_code == 200

    def test_source_pins_hide_a_mature_source_for_the_gated_profile(self, env):
        """Pins resolve through the same gate, so a pin made under the opted-in
        profile cannot surface the source under the other one."""
        client = env["client"]
        pinned = client.put(
            "/sources/pins",
            json={"source_ids": [MATURE_SOURCE]},
            headers={"X-Profile-Id": str(env["on"])},
        )
        assert pinned.status_code == 200
        assert pinned.json()[0]["available"] is True
        # The other profile has its own pin set; it must not be able to pin the
        # source at all while its gate is off.
        rejected = client.put(
            "/sources/pins",
            json={"source_ids": [MATURE_SOURCE]},
            headers={"X-Profile-Id": str(env["off"])},
        )
        assert rejected.status_code >= 400

    # -- local series ------------------------------------------------------

    def test_library_grid_hides_the_adult_series_and_keeps_the_total_honest(self, env):
        client = env["client"]
        gated = client.get(
            "/library/series", headers={"X-Profile-Id": str(env["off"])}
        ).json()
        opted_in = client.get(
            "/library/series", headers={"X-Profile-Id": str(env["on"])}
        ).json()

        assert {item["title"] for item in gated["items"]} == {"Wholesome Adventure"}
        assert {"Wholesome Adventure", "Adults Only"} == {
            item["title"] for item in opted_in["items"]
        }
        # The total must agree with the page, or the client renders a phantom
        # page for a row it can never fetch.
        assert gated["total"] == len(gated["items"]) == 1
        assert opted_in["total"] == len(opted_in["items"]) == 2

    def test_library_search_hides_the_adult_series(self, env):
        client = env["client"]
        gated = client.get(
            "/library/search",
            params={"q": "Only"},
            headers={"X-Profile-Id": str(env["off"])},
        ).json()
        opted_in = client.get(
            "/library/search",
            params={"q": "Only"},
            headers={"X-Profile-Id": str(env["on"])},
        ).json()

        assert gated["items"] == []
        assert {item["title"] for item in opted_in["items"]} == {"Adults Only"}

    def test_series_detail_for_a_hidden_series_is_404(self, env):
        client = env["client"]
        blocked = client.get(
            f"/library/series/{env['adult']}", headers={"X-Profile-Id": str(env["off"])}
        )
        assert blocked.status_code == 404

        allowed = client.get(
            f"/library/series/{env['adult']}", headers={"X-Profile-Id": str(env["on"])}
        )
        assert allowed.status_code == 200
        assert allowed.json()["title"] == "Adults Only"

    def test_statistics_and_discovery_exclude_the_adult_series(self, env):
        client = env["client"]
        h_off = {"X-Profile-Id": str(env["off"])}
        h_on = {"X-Profile-Id": str(env["on"])}

        assert client.get("/library/statistics", headers=h_off).json()["total_series"] == 1
        assert client.get("/library/statistics", headers=h_on).json()["total_series"] == 2

        recent_off = {r["title"] for r in client.get("/library/recently-added", headers=h_off).json()}
        recent_on = {r["title"] for r in client.get("/library/recently-added", headers=h_on).json()}
        assert "Adults Only" not in recent_off
        assert "Adults Only" in recent_on

    def test_continue_reading_does_not_resurface_a_hidden_series(self, env):
        """Hiding from the grid but not from Continue Reading would put the
        cover on the home screen -- worse than not hiding at all."""
        client = env["client"]
        off = {
            r["series_title"]
            for r in client.get(
                "/library/continue-reading", headers={"X-Profile-Id": str(env["off"])}
            ).json()
        }
        on = {
            r["series_title"]
            for r in client.get(
                "/library/continue-reading", headers={"X-Profile-Id": str(env["on"])}
            ).json()
        }
        assert off == {"Wholesome Adventure"}
        assert on == {"Wholesome Adventure", "Adults Only"}

    def test_hiding_never_deletes(self, env):
        """The gate is a visibility filter: the rows, the membership and the
        progress all survive and come back when the profile opts in."""
        client, off = env["client"], env["off"]
        assert client.get(
            "/library/series", headers={"X-Profile-Id": str(off)}
        ).json()["total"] == 1

        db = env["factory"]()
        try:
            assert db.get(Series, env["adult"]) is not None
            assert (
                db.query(UserSeriesState)
                .filter(
                    UserSeriesState.profile_id == off,
                    UserSeriesState.series_id == env["adult"],
                    UserSeriesState.in_library == True,  # noqa: E712
                )
                .count()
                == 1
            )
            assert (
                db.query(ReadingProgress)
                .filter(
                    ReadingProgress.profile_id == off,
                    ReadingProgress.series_id == env["adult"],
                )
                .count()
                == 1
            )
        finally:
            db.close()

        _set_gate(client, off, True)
        titles = {
            item["title"]
            for item in client.get(
                "/library/series", headers={"X-Profile-Id": str(off)}
            ).json()["items"]
        }
        assert titles == {"Wholesome Adventure", "Adults Only"}

    # -- followed remote series -------------------------------------------

    def test_followed_series_on_a_mature_source_is_hidden_for_the_gated_profile(self, env):
        """A follow has no local Series row to read a rating off, so its
        maturity is resolved from the source it lives on."""
        client, factory = env["client"], env["factory"]
        db = factory()
        try:
            for profile_id in (env["off"], env["on"]):
                db.add_all(
                    [
                        SeriesTracker(
                            user_id=env["owner_id"],
                            profile_id=profile_id,
                            source=MATURE_SOURCE,
                            series_id="adult-1",
                            series_title="Adult Follow",
                            track_kind="followed",
                        ),
                        SeriesTracker(
                            user_id=env["owner_id"],
                            profile_id=profile_id,
                            source=SAFE_SOURCE,
                            series_id="safe-1",
                            series_title="Safe Follow",
                            track_kind="followed",
                        ),
                    ]
                )
            db.commit()
        finally:
            db.close()

        gated = client.get("/updates/trackers", headers={"X-Profile-Id": str(env["off"])})
        opted_in = client.get("/updates/trackers", headers={"X-Profile-Id": str(env["on"])})

        assert {t["series_title"] for t in gated.json()} == {"Safe Follow"}
        assert {t["series_title"] for t in opted_in.json()} == {
            "Safe Follow",
            "Adult Follow",
        }
        # The count header agrees with the body, and the hidden ones are
        # reported rather than vanishing without explanation.
        assert gated.headers["X-Total-Count"] == "1"
        assert gated.headers["X-Hidden-By-Mature-Gate"] == "1"
        assert opted_in.headers["X-Hidden-By-Mature-Gate"] == "0"

    def test_content_rating_and_override_drive_visibility_on_a_safe_source(self, env):
        """Rules 2 and 1 of the resolution order, on a source that is itself
        general-purpose -- the case source maturity alone cannot catch."""
        client, factory = env["client"], env["factory"]
        db = factory()
        try:
            rated = SeriesTracker(
                user_id=env["owner_id"],
                profile_id=env["off"],
                source=SAFE_SOURCE,
                series_id="rated-1",
                series_title="Rated Smut",
                track_kind="followed",
                content_rating="smut",
            )
            plain = SeriesTracker(
                user_id=env["owner_id"],
                profile_id=env["off"],
                source=SAFE_SOURCE,
                series_id="plain-1",
                series_title="Unrated Thing",
                track_kind="followed",
            )
            db.add_all([rated, plain])
            db.commit()
            plain_id = plain.id
        finally:
            db.close()

        h = {"X-Profile-Id": str(env["off"])}
        visible = client.get("/updates/trackers", headers=h).json()
        assert {t["series_title"] for t in visible} == {"Unrated Thing"}
        # Unknown is a third state, surfaced and badged rather than folded into
        # either "safe" or "mature".
        assert visible[0]["rating"] == "unknown"

        # The user's explicit override wins and hides it immediately.
        patched = client.patch(
            f"/updates/trackers/{plain_id}", json={"mature_override": True}, headers=h
        )
        assert patched.status_code == 200
        assert patched.json()["rating"] == "mature"
        assert client.get("/updates/trackers", headers=h).json() == []

        # An explicit null clears the override and restores inference.
        client.patch(
            f"/updates/trackers/{plain_id}", json={"mature_override": None}, headers=h
        )
        assert len(client.get("/updates/trackers", headers=h).json()) == 1

    def test_override_can_also_force_a_mature_source_follow_visible(self, env):
        """The inverse: a general title on an adult source, marked not-18+."""
        client, factory = env["client"], env["factory"]
        db = factory()
        try:
            row = SeriesTracker(
                user_id=env["owner_id"],
                profile_id=env["off"],
                source=MATURE_SOURCE,
                series_id="sfw-1",
                series_title="Actually Fine",
                track_kind="followed",
            )
            db.add(row)
            db.commit()
            tracker_id = row.id
        finally:
            db.close()

        h = {"X-Profile-Id": str(env["off"])}
        assert client.get("/updates/trackers", headers=h).json() == []
        client.patch(
            f"/updates/trackers/{tracker_id}", json={"mature_override": False}, headers=h
        )
        assert len(client.get("/updates/trackers", headers=h).json()) == 1

    # -- write-side back doors --------------------------------------------

    def test_following_a_mature_source_is_refused_while_the_gate_is_off(self, env):
        client = env["client"]
        body = {
            "source": MATURE_SOURCE,
            "series_id": "x",
            "series_title": "X",
        }
        blocked = client.post(
            "/updates/trackers/follow",
            json=body,
            headers={"X-Profile-Id": str(env["off"])},
        )
        assert blocked.status_code == 400

        allowed = client.post(
            "/updates/trackers/follow",
            json=body,
            headers={"X-Profile-Id": str(env["on"])},
        )
        assert allowed.status_code == 200

    def test_updates_source_list_is_gated(self, env):
        client = env["client"]
        off = {
            s["source_type"]
            for s in client.get(
                "/updates/sources", headers={"X-Profile-Id": str(env["off"])}
            ).json()
        }
        on = {
            s["source_type"]
            for s in client.get(
                "/updates/sources", headers={"X-Profile-Id": str(env["on"])}
            ).json()
        }
        assert MATURE_SOURCE not in off
        assert MATURE_SOURCE in on

    def test_queueing_a_download_from_a_mature_source_is_refused(self, env):
        client = env["client"]
        blocked = client.post(
            "/downloads/chapters",
            json={
                "source_id": MATURE_SOURCE,
                "series_id": "s1",
                "chapter_ids": ["c1"],
            },
            headers={"X-Profile-Id": str(env["off"])},
        )
        assert blocked.status_code == 404
        assert blocked.json()["code"] == "source_not_found"

    def test_genres_supplied_at_follow_time_become_the_rating(self, env):
        """The client already has the genres from the series page it is
        following from, so the rating is captured without a scraper round-trip."""
        client = env["client"]
        follow = client.post(
            "/updates/trackers/follow",
            json={
                "source": SAFE_SOURCE,
                "series_id": "g1",
                "series_title": "Genre Tagged",
                "genres": ["Romance", "Adult"],
            },
            headers={"X-Profile-Id": str(env["on"])},
        )
        assert follow.status_code == 200
        assert follow.json()["content_rating"] == "adult"
        assert follow.json()["rating"] == "mature"
        # ...and it is therefore hidden from the profile with 18+ off, even
        # though the source itself is general-purpose.
        assert client.get(
            "/updates/trackers", headers={"X-Profile-Id": str(env["off"])}
        ).json() == []

    # -- independence ------------------------------------------------------

    def test_toggling_one_profile_never_moves_the_other(self, env):
        client, off, on = env["client"], env["off"], env["on"]

        def visible(profile_id: int) -> set[str]:
            return {
                item["title"]
                for item in client.get(
                    "/library/series", headers={"X-Profile-Id": str(profile_id)}
                ).json()["items"]
            }

        assert visible(off) == {"Wholesome Adventure"}
        assert visible(on) == {"Wholesome Adventure", "Adults Only"}

        # Turn the opted-in profile OFF: the other one must not move.
        _set_gate(client, on, False)
        assert visible(on) == {"Wholesome Adventure"}
        assert visible(off) == {"Wholesome Adventure"}

        # Turn the previously-gated profile ON: again, no cross-talk.
        _set_gate(client, off, True)
        assert visible(off) == {"Wholesome Adventure", "Adults Only"}
        assert visible(on) == {"Wholesome Adventure"}

    def test_the_global_flag_does_not_override_an_active_profile(self, env):
        """The global value is the fallback for the unscoped bucket and the seed
        for new profiles -- never an override. A profile-less PUT /settings from
        the web client used to flip it on and defeat every profile's gate."""
        client = env["client"]
        update_persisted_settings(mature_content_enabled=True)
        try:
            titles = {
                item["title"]
                for item in client.get(
                    "/library/series", headers={"X-Profile-Id": str(env["off"])}
                ).json()["items"]
            }
            assert titles == {"Wholesome Adventure"}
            assert MATURE_SOURCE not in {
                s["id"]
                for s in client.get(
                    "/sources", headers={"X-Profile-Id": str(env["off"])}
                ).json()
            }
        finally:
            update_persisted_settings(mature_content_enabled=False)


# ── rating-rule unit coverage (no HTTP) ──────────────────────────────────────


def test_whitespace_padded_rating_is_still_mature_in_sql_and_python(db_session):
    """The Python rule strips, the SQL rule used not to, so a stored " adult"
    was adult in one layer and safe in the other."""
    from core.content_rating import is_mature_rating
    from services.library_intelligence_service import LibraryIntelligenceService

    lib = Library(name="L", root_path="/l")
    db_session.add(lib)
    db_session.flush()
    padded = Series(
        library_id=lib.id,
        title="Padded",
        folder_path="/l/p",
        sort_title="padded",
        content_rating="  Adult  ",
    )
    db_session.add(padded)
    db_session.flush()
    db_session.add(
        UserSeriesState(user_id=None, profile_id=None, series_id=padded.id, in_library=True)
    )
    db_session.commit()

    assert is_mature_rating("  Adult  ") is True
    titles = {
        r["title"]
        for r in LibraryIntelligenceService(db_session).get_recently_added(limit=10)
    }
    assert "Padded" not in titles


def test_unrated_series_stays_visible_while_the_gate_is_off(db_session):
    """Unknown is deliberately not folded into mature for LOCAL series:
    ``Series.content_rating`` defaults to "unknown" for every folder import, so
    hiding unknown would blank the whole library the first time the gate is
    turned off."""
    from services.library_intelligence_service import LibraryIntelligenceService

    lib = Library(name="L", root_path="/l")
    db_session.add(lib)
    db_session.flush()
    unrated = Series(
        library_id=lib.id, title="Unrated", folder_path="/l/u", sort_title="unrated"
    )
    db_session.add(unrated)
    db_session.flush()
    assert unrated.content_rating == "unknown"
    db_session.add(
        UserSeriesState(user_id=None, profile_id=None, series_id=unrated.id, in_library=True)
    )
    db_session.commit()

    titles = {
        r["title"]
        for r in LibraryIntelligenceService(db_session).get_recently_added(limit=10)
    }
    assert "Unrated" in titles

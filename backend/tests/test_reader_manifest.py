"""``GET /reader/chapter/manifest`` — the client download plan (spec §4.1, §7).

The manifest is the ordered page list (number + proxy URL), chapter number, and
prev/next chapter keys. No bytes. Tested against a stub connector.
"""

from __future__ import annotations

import pytest

from core.errors import AppError
from services.browse_service import get_browse_service
from services.reader_service import ReaderService
from tests._fakes import FakeBrowse

SRC = "mangadex"
SERIES = "omniscient-reader"

FIXTURE = {
    (SRC, SERIES): {
        "meta": {"title": "Omniscient Reader"},
        "chapters": [
            {"id": "ch-1", "number": 1.0, "title": "Prologue"},
            {"id": "ch-2", "number": 2.0, "title": "Episode 1"},
            {"id": "ch-3", "number": 3.0, "title": "Episode 2"},
        ],
        "pages": {
            "ch-2": [
                {"number": 1, "image_url": "/sources/mangadex/pages/p1/image"},
                {"number": 2, "image_url": "/sources/mangadex/pages/p2/image"},
                {"number": 3, "image_url": "/sources/mangadex/pages/p3/image"},
            ]
        },
    }
}


def test_manifest_shape(db_session):
    svc = ReaderService(FakeBrowse(FIXTURE))
    m = svc.manifest(SRC, SERIES, "ch-2")

    assert m["source_id"] == SRC
    assert m["series_key"] == SERIES
    assert m["chapter_key"] == "ch-2"
    assert m["chapter_number"] == 2.0
    assert m["page_count"] == 3
    assert m["pages"] == [
        {"number": 1, "url": "/sources/mangadex/pages/p1/image"},
        {"number": 2, "url": "/sources/mangadex/pages/p2/image"},
        {"number": 3, "url": "/sources/mangadex/pages/p3/image"},
    ]
    assert m["prev"] == "ch-1"
    assert m["next"] == "ch-3"
    # no bytes, no hashes in v1
    assert "sha256" not in m["pages"][0]


def test_manifest_prev_none_at_first_chapter(db_session):
    fixture = {
        (SRC, SERIES): {
            **FIXTURE[(SRC, SERIES)],
            "pages": {"ch-1": [{"number": 1, "image_url": "/x"}]},
        }
    }
    m = ReaderService(FakeBrowse(fixture)).manifest(SRC, SERIES, "ch-1")
    assert m["prev"] is None
    assert m["next"] == "ch-2"


def test_manifest_unknown_chapter_is_404(db_session):
    svc = ReaderService(FakeBrowse(FIXTURE))
    with pytest.raises(AppError) as exc:
        svc.manifest(SRC, SERIES, "ch-does-not-exist")
    assert exc.value.status_code == 404


def test_manifest_endpoint(app, client):
    app.dependency_overrides[get_browse_service] = lambda: FakeBrowse(FIXTURE)
    resp = client.get(
        "/reader/chapter/manifest",
        params={"source": SRC, "series": SERIES, "chapter": "ch-2"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["page_count"] == 3
    assert body["next"] == "ch-3"

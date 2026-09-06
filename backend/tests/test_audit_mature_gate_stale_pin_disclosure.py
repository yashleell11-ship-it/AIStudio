"""Audit (shard: mature-gate): a pin created while the mature gate was open is
still returned by GET /sources/pins after the gate is shut, carrying the raw
adult connector id in both ``source_id`` and ``name``.

Every other route answers 404 for that id when the gate is closed; this one
hands the id to the gated profile. Expected to FAIL until list_pins() omits
pins whose (ungated) descriptor is mature while the gate is off.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.config import get_settings
from database.models import SourcePin
from tests.test_source_pins import (
    PIN_REGISTRY,
    _FakeDescriptor,
    _fake_registry,
    _make_client,
    _register,
)


@pytest.mark.real_auth
def test_stale_adult_pin_is_not_returned_when_gate_is_off(db_engine, monkeypatch):
    monkeypatch.setenv("MM_COOKIE_SECURE", "false")
    monkeypatch.setenv("MM_MATURE_CONTENT_ENABLED", "false")
    get_settings.cache_clear()
    try:
        client, factory = _make_client(db_engine)
        user_id = _register(client, "owner")

        # Row written while the gate was open (bypasses PUT validation on purpose).
        db = factory()
        try:
            db.add(SourcePin(user_id=user_id, profile_id=None, source_id="adult", sort_order=0))
            db.commit()
        finally:
            db.close()

        registry = _fake_registry(_FakeDescriptor("safe"), _FakeDescriptor("adult", mature=True))
        with patch(PIN_REGISTRY, registry):
            pins = client.get("/sources/pins").json()

        leaked = [p for p in pins if p["source_id"] == "adult"]
        assert not leaked, f"gated profile received adult source id via stale pin: {leaked}"
    finally:
        get_settings.cache_clear()

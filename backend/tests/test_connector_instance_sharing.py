"""Every configless connector must be ONE shared instance per process.

The bulk chapter windows (spec 2026-09-05 R2/R5) fetch several chapters of a
source at once, and their entire claim to politeness is that they do not build a
second fetching layer: the shared per-source connector holds one pooled,
keep-alive ``httpx.Client`` and one ``min_interval`` rate lock, so four worker
threads asking the same site for four chapters still leave 0.21 s between
requests.

That claim is only true while ``create_connector`` returns the same instance
every time. Two connectors (webtoons, weebcentral) were missing from
``_CONFIGLESS_CONNECTORS`` despite taking no constructor arguments, which built
a fresh client and fresh TTL caches per call — and, concurrently, four
unsynchronised clients with no shared spacing at all. This pins the general
rule so the next connector added does not reopen it.
"""

from __future__ import annotations

import inspect

import pytest

import connectors.registry as registry
from connectors.registry import create_connector, list_connector_types
from core.config import get_settings

#: The one connector that genuinely needs config (``root_path``) and therefore
#: cannot be a process-wide singleton.
CONFIGURED = {"local_filesystem"}


@pytest.fixture
def novels_on(monkeypatch):
    """Novel connectors do not exist at all while the flag is off, so the sweep
    below would silently skip six sources."""
    monkeypatch.setenv("MM_NOVELS_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _takes_no_config(source_type: str) -> bool:
    cls = registry._REGISTRY[source_type]
    params = list(inspect.signature(cls.__init__).parameters.values())[1:]
    return all(p.default is not inspect.Parameter.empty for p in params)


def test_every_configless_connector_is_shared(novels_on):
    offenders = []
    for source_type in sorted(list_connector_types()):
        if source_type in CONFIGURED or not _takes_no_config(source_type):
            continue
        if create_connector(source_type) is not create_connector(source_type):
            offenders.append(source_type)
    assert offenders == [], (
        "these connectors take no config but are rebuilt on every call — each "
        "gets its own HTTP client, its own empty TTL caches and its own "
        "min_interval, so concurrent reads of the source are not spaced: "
        f"{offenders}. Add them to connectors.registry._CONFIGLESS_CONNECTORS."
    )


def test_the_shared_instance_shares_its_http_client(novels_on):
    """Not just the same object — the same client, which is the pool and the
    rate lock the bulk windows depend on."""
    for source_type in ("webtoons", "weebcentral", "asurascans", "freewebnovel"):
        first = create_connector(source_type)
        second = create_connector(source_type)
        assert first is second, source_type
        client = getattr(first, "_http", None)
        if client is not None:
            assert client is getattr(second, "_http"), source_type


def test_a_configured_connector_is_still_built_per_call(tmp_path):
    """``local_filesystem`` must NOT be cached: its whole identity is the
    ``root_path`` it was handed."""
    a = create_connector("local_filesystem", root_path=str(tmp_path))
    b = create_connector("local_filesystem", root_path=str(tmp_path))
    assert a is not b

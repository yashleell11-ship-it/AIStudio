"""Process-lifetime index over the connector registry.

``connectors.registry.list_installed_connectors()`` rebuilds every
``ConnectorDescriptor`` from scratch and re-sorts the list on every call — ~50
dataclass constructions, each of which computes an icon URL. That is fine once
per response and ruinous once per *row*: the library serializer resolves a 18+
rating per followed series, and each resolution asked the registry for the
whole list and scanned it linearly. A 300-series library therefore built ~15600
descriptors to answer 300 questions of the form "is this source id adult?".

This module answers those questions from a dict built once. The registry is
static after import (``_register_builtin_connectors()`` runs at module import
and nothing registers later in production), so the only input that can change
within a process is the ``MM_NOVELS_ENABLED`` flag — which the registry itself
re-reads per call so both states stay testable in one process. The cache is
therefore keyed on that flag rather than being unconditional: flipping it (as
``tests/test_novels_flag.py`` does) rebuilds the index instead of serving a
stale one.

Read-only: nothing here mutates the registry, and callers that need the full
descriptor list for a *response* should keep calling the registry directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from connectors.registry import list_installed_connectors
from core.config import get_settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from connectors.registry import ConnectorDescriptor

#: (novels_enabled, registry size) -> index. The registry size is part of the
#: key so a test that registers an extra connector into ``_REGISTRY`` is not
#: served a stale index; it costs one ``len()`` per lookup.
_CACHE: dict[tuple[bool, int], dict[str, "ConnectorDescriptor"]] = {}


def _cache_key() -> tuple[bool, int]:
    from connectors.registry import _REGISTRY

    return (bool(getattr(get_settings(), "novels_enabled", False)), len(_REGISTRY))


def descriptors_by_source() -> dict[str, "ConnectorDescriptor"]:
    """``source_type -> ConnectorDescriptor`` for every installed connector.

    The returned dict is shared and must not be mutated by callers.
    """
    key = _cache_key()
    index = _CACHE.get(key)
    if index is None:
        index = {d.source_type: d for d in list_installed_connectors()}
        _CACHE[key] = index
    return index


def descriptor_for_source(source_id: str) -> "ConnectorDescriptor | None":
    """The descriptor for one source id, or ``None`` when it is not installed."""
    return descriptors_by_source().get(source_id)


def mature_source_ids() -> tuple[str, ...]:
    """Sorted ids of the sources that are adult by nature.

    Sorted so the tuple is a stable SQL ``IN`` parameter list — an unstable
    order would give SQLAlchemy a different cache key for the same query.
    """
    return tuple(sorted(d.source_type for d in descriptors_by_source().values() if d.mature))


def reset_cache() -> None:
    """Drop the memo. For tests that mutate the registry in place."""
    _CACHE.clear()

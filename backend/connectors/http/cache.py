"""TTL cache for connector metadata."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._entries: dict[str, tuple[float, T]] = {}

    def get(self, key: str) -> T | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            self._entries.pop(key, None)
            return None
        return value

    def set(self, key: str, value: T) -> None:
        self._entries[key] = (time.monotonic() + self._ttl, value)

    def pop(self, key: str) -> None:
        """Drop a cached entry so the next lookup refetches."""
        self._entries.pop(key, None)

    def get_or_set(self, key: str, factory: Callable[[], T]) -> T:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = factory()
        self.set(key, value)
        return value

    def clear(self) -> None:
        self._entries.clear()

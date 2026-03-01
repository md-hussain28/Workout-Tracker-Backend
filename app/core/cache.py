"""Simple in-memory TTL cache for rarely-changing data (exercises, muscle groups)."""

from __future__ import annotations

import time
from typing import Any


class TTLCache:
    """Thread-safe-ish in-memory cache with TTL. Invalidates by key prefix."""

    def __init__(self, ttl_seconds: float = 300):
        self._cache: dict[str, tuple[Any, float]] = {}
        self._ttl = ttl_seconds

    def get(self, key: str) -> Any | None:
        if key not in self._cache:
            return None
        val, expires = self._cache[key]
        if time.monotonic() > expires:
            del self._cache[key]
            return None
        return val

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = (value, time.monotonic() + self._ttl)

    def invalidate_prefix(self, prefix: str) -> None:
        """Remove all keys starting with prefix (e.g. 'exercises:' to clear exercise caches)."""
        to_remove = [k for k in self._cache if k.startswith(prefix)]
        for k in to_remove:
            del self._cache[k]


# Shared cache instance (5 min TTL)
app_cache = TTLCache(ttl_seconds=300)

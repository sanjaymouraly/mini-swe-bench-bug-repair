"""Cache telemetry statistics."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    sets: int = 0
    lru_evictions: int = 0
    expired_evictions: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return (self.hits / total) if total > 0 else 0.0

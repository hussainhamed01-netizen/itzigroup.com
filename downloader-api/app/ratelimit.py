"""Per-client sliding-window rate limiting."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, window: float = 60.0):
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int) -> float | None:
        """Record a request. Returns None when allowed, else seconds until a retry may succeed."""
        if limit <= 0:
            return None
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= limit:
                return max(1.0, hits[0] + self.window - now)
            hits.append(now)
            return None

    def sweep(self) -> None:
        cutoff = time.monotonic() - self.window
        with self._lock:
            for key in [k for k, hits in self._hits.items() if not hits or hits[-1] <= cutoff]:
                del self._hits[key]

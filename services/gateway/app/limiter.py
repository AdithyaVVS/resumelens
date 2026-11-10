import time
from collections import defaultdict, deque


class RateLimiter:
    """Allows `limit` hits per `window` seconds for each key. Kept in memory,
    so it is per server instance and resets on restart."""

    def __init__(self, limit: int, window: float = 60.0):
        self.limit = limit
        self.window = window
        self.hits = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        recent = self.hits[key]
        while recent and now - recent[0] > self.window:
            recent.popleft()
        if len(recent) >= self.limit:
            return False
        recent.append(now)
        return True

    def reset(self) -> None:
        self.hits.clear()

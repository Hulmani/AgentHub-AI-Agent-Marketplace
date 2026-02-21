import os
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Depends, HTTPException, status

from .auth import get_api_key


class InMemoryRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._store: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> tuple[bool, int]:
        now = time.time()
        with self._lock:
            bucket = self._store[key]
            while bucket and (now - bucket[0]) > self.window_seconds:
                bucket.popleft()

            if len(bucket) >= self.max_requests:
                retry_after = max(1, int(self.window_seconds - (now - bucket[0])))
                return False, retry_after

            bucket.append(now)
            return True, 0


rate_limiter = InMemoryRateLimiter(
    max_requests=int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "120")),
    window_seconds=int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")),
)


def enforce_rate_limit(api_key: str = Depends(get_api_key)) -> None:
    allowed, retry_after = rate_limiter.allow(api_key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded.",
            headers={"Retry-After": str(retry_after)},
        )


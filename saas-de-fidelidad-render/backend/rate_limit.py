from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Protocol
from uuid import uuid4

import redis


class RateLimiter(Protocol):
    def reset(self) -> None: ...

    def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]: ...


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def reset(self) -> None:
        self._events.clear()

    def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.monotonic()
        window_start = now - window_seconds
        events = self._events[key]

        while events and events[0] <= window_start:
            events.popleft()

        if len(events) >= limit:
            retry_after = max(1, int(events[0] + window_seconds - now))
            return False, retry_after

        events.append(now)
        return True, 0


class RedisSlidingWindowRateLimiter:
    def __init__(self, client: redis.Redis, prefix: str = "rate-limit") -> None:
        self.client = client
        self.prefix = prefix

    def reset(self) -> None:
        for key in self.client.scan_iter(f"{self.prefix}:*"):
            self.client.delete(key)

    def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now_ms = int(time.time() * 1000)
        window_start_ms = now_ms - (window_seconds * 1000)
        redis_key = f"{self.prefix}:{key}"

        cleanup_pipe = self.client.pipeline(transaction=True)
        cleanup_pipe.zremrangebyscore(redis_key, 0, window_start_ms)
        cleanup_pipe.zcard(redis_key)
        cleanup_pipe.zrange(redis_key, 0, 0, withscores=True)
        _, current_count, oldest = cleanup_pipe.execute()

        if current_count >= limit:
            retry_after = 1
            if oldest:
                oldest_score = int(oldest[0][1])
                retry_after = max(1, int((oldest_score + (window_seconds * 1000) - now_ms) / 1000))
            return False, retry_after

        add_pipe = self.client.pipeline(transaction=True)
        add_pipe.zadd(redis_key, {f"{now_ms}:{uuid4().hex}": now_ms})
        add_pipe.expire(redis_key, window_seconds + 1)
        add_pipe.execute()
        return True, 0


def build_rate_limiter(redis_url: str | None) -> tuple[RateLimiter, str]:
    if not redis_url:
        return SlidingWindowRateLimiter(), "memory"

    try:
        client = redis.Redis.from_url(redis_url, decode_responses=True)
        client.ping()
    except redis.RedisError:
        return SlidingWindowRateLimiter(), "memory"

    return RedisSlidingWindowRateLimiter(client), "redis"
"""
Rate Limiter — token-bucket rate limiting using Redis.

Provides per-key rate limiting for API endpoints.
Falls back to in-memory dict if Redis is unavailable.
"""

import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token-bucket rate limiter backed by Redis (with in-memory fallback)."""

    def __init__(
        self,
        redis_url: str = None,
        default_rpm: int = 60,
    ):
        """
        Args:
            redis_url: Redis connection URL (e.g. redis://localhost:6379/0).
            default_rpm: Default requests per minute.
        """
        self.default_rpm = default_rpm
        self._redis = None
        self._fallback: dict[str, list] = {}  # key -> [timestamps]

        if redis_url:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(redis_url, decode_responses=True)
                logger.info("RateLimiter using Redis backend")
            except Exception as e:
                logger.warning(f"Redis unavailable for rate limiter, using memory: {e}")

    async def check(self, key: str, limit: int = None) -> bool:
        """Check if a request is allowed under the rate limit.

        Args:
            key: Rate limit bucket key (e.g. "ip:1.2.3.4" or "user:admin@x.com").
            limit: Override RPM for this check. Defaults to self.default_rpm.

        Returns:
            True if the request is allowed, False if rate limited.
        """
        limit = limit or self.default_rpm

        if self._redis:
            return await self._check_redis(key, limit)
        return self._check_memory(key, limit)

    async def _check_redis(self, key: str, limit: int) -> bool:
        """Redis-backed sliding window rate check."""
        try:
            redis_key = f"rate:{key}"
            now = time.time()
            window = 60  # 1 minute window

            pipe = self._redis.pipeline()
            pipe.zremrangebyscore(redis_key, 0, now - window)
            pipe.zcard(redis_key)
            pipe.zadd(redis_key, {str(now): now})
            pipe.expire(redis_key, window + 1)
            results = await pipe.execute()

            count = results[1]
            return count < limit

        except Exception as e:
            logger.warning(f"Redis rate check failed, allowing: {e}")
            return True

    def _check_memory(self, key: str, limit: int) -> bool:
        """In-memory fallback rate check."""
        now = time.time()
        window = 60

        if key not in self._fallback:
            self._fallback[key] = []

        # Remove expired entries
        self._fallback[key] = [
            ts for ts in self._fallback[key] if ts > now - window
        ]

        if len(self._fallback[key]) >= limit:
            return False

        self._fallback[key].append(now)
        return True

    async def get_remaining(self, key: str, limit: int = None) -> int:
        """Get remaining requests in the current window."""
        limit = limit or self.default_rpm

        if self._redis:
            try:
                redis_key = f"rate:{key}"
                now = time.time()
                await self._redis.zremrangebyscore(redis_key, 0, now - 60)
                count = await self._redis.zcard(redis_key)
                return max(0, limit - count)
            except Exception:
                return limit

        timestamps = self._fallback.get(key, [])
        now = time.time()
        active = [ts for ts in timestamps if ts > now - 60]
        return max(0, limit - len(active))

    async def reset(self, key: str):
        """Reset rate limit for a key."""
        if self._redis:
            try:
                await self._redis.delete(f"rate:{key}")
            except Exception:
                pass
        self._fallback.pop(key, None)

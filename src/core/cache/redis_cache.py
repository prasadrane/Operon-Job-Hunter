"""Redis cache with in-memory dict fallback when Redis unavailable."""

import asyncio
import json
import time
import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class RedisCache:
    """
    Async cache with Redis backend and in-memory fallback.

    If Redis is unavailable or not configured, falls back to a thread-safe
    in-memory dict with TTL support. Application works without Redis.
    """

    def __init__(self, redis_url: Optional[str] = None, default_ttl: int = 3600):
        """
        Initialize cache.

        Args:
            redis_url: Redis connection URL (e.g. "redis://localhost:6379/0").
                       If None or connection fails, uses in-memory fallback.
            default_ttl: Default TTL in seconds for cache entries.
        """
        self._redis_url = redis_url
        self._default_ttl = default_ttl
        self._redis = None
        self._redis_available = False

        # In-memory fallback: {key: (value, expire_time)}
        self._memory_cache: Dict[str, Tuple[Any, float]] = {}
        self._lock = asyncio.Lock()

        # Try to connect to Redis if URL provided
        if redis_url:
            self._try_connect_redis()

    def _try_connect_redis(self) -> None:
        """Attempt Redis connection, fall back to memory on failure."""
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            self._redis_available = True
            logger.info("Redis cache connected: %s", self._redis_url)
        except ImportError:
            logger.warning("redis package not installed, using in-memory cache")
            self._redis_available = False
        except Exception as e:
            logger.warning("Redis connection failed, using in-memory cache: %s", e)
            self._redis_available = False

    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        if self._redis_available and self._redis:
            try:
                val = await self._redis.get(key)
                if val is not None:
                    return json.loads(val)
                return None
            except Exception as e:
                logger.debug("Redis GET failed for key=%s: %s", key, e)
                self._redis_available = False

        # In-memory fallback
        async with self._lock:
            if key in self._memory_cache:
                value, expire_time = self._memory_cache[key]
                if expire_time > time.time():
                    return value
                else:
                    del self._memory_cache[key]
            return None

    async def set(self, key: str, value: Any, ttl_sec: int = None) -> None:
        """
        Set value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache (must be JSON-serializable)
            ttl_sec: Time-to-live in seconds (default: self._default_ttl)
        """
        if ttl_sec is None:
            ttl_sec = self._default_ttl

        if self._redis_available and self._redis:
            try:
                serialized = json.dumps(value)
                await self._redis.setex(key, ttl_sec, serialized)
                return
            except Exception as e:
                logger.debug("Redis SET failed for key=%s: %s", key, e)
                self._redis_available = False

        # In-memory fallback
        async with self._lock:
            expire_time = time.time() + ttl_sec
            self._memory_cache[key] = (value, expire_time)

    async def delete(self, key: str) -> None:
        """
        Delete key from cache.

        Args:
            key: Cache key to delete
        """
        if self._redis_available and self._redis:
            try:
                await self._redis.delete(key)
                return
            except Exception as e:
                logger.debug("Redis DELETE failed for key=%s: %s", key, e)
                self._redis_available = False

        # In-memory fallback
        async with self._lock:
            self._memory_cache.pop(key, None)

    async def exists(self, key: str) -> bool:
        """
        Check if key exists in cache (and not expired).

        Args:
            key: Cache key

        Returns:
            True if key exists and not expired
        """
        if self._redis_available and self._redis:
            try:
                result = await self._redis.exists(key)
                return bool(result)
            except Exception as e:
                logger.debug("Redis EXISTS failed for key=%s: %s", key, e)
                self._redis_available = False

        # In-memory fallback
        async with self._lock:
            if key in self._memory_cache:
                _, expire_time = self._memory_cache[key]
                if expire_time > time.time():
                    return True
                else:
                    del self._memory_cache[key]
            return False

    async def close(self) -> None:
        """Close Redis connection if open."""
        if self._redis:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            self._redis = None
        self._memory_cache.clear()

    @property
    def is_redis_available(self) -> bool:
        """Check if Redis is currently available."""
        return self._redis_available

"""Unit tests for RedisCache with in-memory fallback."""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.cache.redis_cache import RedisCache


@pytest.fixture
def memory_cache():
    """Create an in-memory cache (no Redis)."""
    return RedisCache(redis_url=None, default_ttl=60)


class TestRedisCacheInMemory:
    """Test in-memory fallback behavior."""

    @pytest.mark.asyncio
    async def test_get_set_basic(self, memory_cache):
        """Test basic get/set operations."""
        await memory_cache.set("key1", "value1")
        result = await memory_cache.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_missing_key(self, memory_cache):
        """Test get returns None for missing key."""
        result = await memory_cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_with_ttl(self, memory_cache):
        """Test TTL expiration."""
        await memory_cache.set("key1", "value1", ttl_sec=1)
        result = await memory_cache.get("key1")
        assert result == "value1"

        # Wait for expiration
        await asyncio.sleep(1.1)
        result = await memory_cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, memory_cache):
        """Test delete operation."""
        await memory_cache.set("key1", "value1")
        await memory_cache.delete("key1")
        result = await memory_cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_missing_key(self, memory_cache):
        """Test delete doesn't error on missing key."""
        await memory_cache.delete("nonexistent")  # Should not raise

    @pytest.mark.asyncio
    async def test_exists_true(self, memory_cache):
        """Test exists returns True for existing key."""
        await memory_cache.set("key1", "value1")
        assert await memory_cache.exists("key1") is True

    @pytest.mark.asyncio
    async def test_exists_false(self, memory_cache):
        """Test exists returns False for missing key."""
        assert await memory_cache.exists("nonexistent") is False

    @pytest.mark.asyncio
    async def test_exists_expired_key(self, memory_cache):
        """Test exists returns False for expired key."""
        await memory_cache.set("key1", "value1", ttl_sec=1)
        await asyncio.sleep(1.1)
        assert await memory_cache.exists("key1") is False

    @pytest.mark.asyncio
    async def test_complex_value_dict(self, memory_cache):
        """Test caching complex dict values."""
        value = {"name": "test", "count": 42, "nested": {"a": 1}}
        await memory_cache.set("complex", value)
        result = await memory_cache.get("complex")
        assert result == value

    @pytest.mark.asyncio
    async def test_complex_value_list(self, memory_cache):
        """Test caching list values."""
        value = [1, 2, 3, "four", {"five": 5}]
        await memory_cache.set("list", value)
        result = await memory_cache.get("list")
        assert result == value

    @pytest.mark.asyncio
    async def test_overwrite_key(self, memory_cache):
        """Test overwriting existing key."""
        await memory_cache.set("key1", "value1")
        await memory_cache.set("key1", "value2")
        result = await memory_cache.get("key1")
        assert result == "value2"

    @pytest.mark.asyncio
    async def test_is_redis_available_false(self, memory_cache):
        """Test is_redis_available returns False without Redis."""
        assert memory_cache.is_redis_available is False

    @pytest.mark.asyncio
    async def test_close_clears_cache(self, memory_cache):
        """Test close clears in-memory cache."""
        await memory_cache.set("key1", "value1")
        await memory_cache.close()
        result = await memory_cache.get("key1")
        assert result is None


class TestRedisCacheWithRedis:
    """Test Redis backend behavior with mocks."""

    @pytest.mark.asyncio
    async def test_redis_get_success(self):
        """Test successful Redis GET."""
        import json

        cache = RedisCache.__new__(RedisCache)
        cache._redis_url = "redis://localhost:6379"
        cache._default_ttl = 3600
        cache._memory_cache = {}
        cache._lock = asyncio.Lock()

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps("cached_value"))
        cache._redis = mock_redis
        cache._redis_available = True

        result = await cache.get("test_key")
        assert result == "cached_value"
        mock_redis.get.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_redis_set_success(self):
        """Test successful Redis SET."""
        import json

        cache = RedisCache.__new__(RedisCache)
        cache._redis_url = "redis://localhost:6379"
        cache._default_ttl = 3600
        cache._memory_cache = {}
        cache._lock = asyncio.Lock()

        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        cache._redis = mock_redis
        cache._redis_available = True

        await cache.set("test_key", "test_value", ttl_sec=120)
        mock_redis.setex.assert_called_once_with("test_key", 120, json.dumps("test_value"))

    @pytest.mark.asyncio
    async def test_redis_delete_success(self):
        """Test successful Redis DELETE."""
        cache = RedisCache.__new__(RedisCache)
        cache._redis_url = "redis://localhost:6379"
        cache._default_ttl = 3600
        cache._memory_cache = {}
        cache._lock = asyncio.Lock()

        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()
        cache._redis = mock_redis
        cache._redis_available = True

        await cache.delete("test_key")
        mock_redis.delete.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_redis_exists_success(self):
        """Test successful Redis EXISTS."""
        cache = RedisCache.__new__(RedisCache)
        cache._redis_url = "redis://localhost:6379"
        cache._default_ttl = 3600
        cache._memory_cache = {}
        cache._lock = asyncio.Lock()

        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=1)
        cache._redis = mock_redis
        cache._redis_available = True

        result = await cache.exists("test_key")
        assert result is True

    @pytest.mark.asyncio
    async def test_redis_fallback_on_error(self):
        """Test fallback to in-memory when Redis fails."""
        cache = RedisCache.__new__(RedisCache)
        cache._redis_url = "redis://localhost:6379"
        cache._default_ttl = 3600
        cache._memory_cache = {}
        cache._lock = asyncio.Lock()

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=Exception("Connection lost"))
        cache._redis = mock_redis
        cache._redis_available = True

        # First call should fail and fall back to memory
        cache._memory_cache["fallback_key"] = ("memory_value", time.time() + 3600)
        result = await cache.get("fallback_key")
        assert result == "memory_value"
        assert cache._redis_available is False

    @pytest.mark.asyncio
    async def test_try_connect_redis_import_error(self):
        """Test graceful handling when redis package not installed."""
        with patch.dict("sys.modules", {"redis": None, "redis.asyncio": None}):
            cache = RedisCache(redis_url="redis://localhost:6379")
            assert cache._redis_available is False
            assert cache._redis is None

"""
Smoke-тесты для проверки подключения к Tarantool и базовых операций.

Эти тесты проверяют:
- Подключение к Tarantool (или корректный fallback на in-memory)
- Базовые операции CRUD в cache
- Базовые операции с threads
- Метрики кэша
"""

import pytest

from app.storage.tarantool import TarantoolClient


@pytest.mark.asyncio
async def test_tarantool_singleton_instance():
    """Проверка, что TarantoolClient возвращает singleton."""
    client1 = await TarantoolClient.get_instance()
    client2 = await TarantoolClient.get_instance()
    assert client1 is client2


@pytest.mark.asyncio
async def test_tarantool_connection_or_fallback():
    """Проверка, что клиент подключен (или в режиме fallback)."""
    client = await TarantoolClient.get_instance()
    assert client._connected is True


@pytest.mark.asyncio
async def test_cache_set_and_get():
    """Проверка базовых операций set/get в кэше."""
    client = await TarantoolClient.get_instance()
    
    test_key = "smoke_test_key"
    test_value = {"data": "smoke_test_value", "number": 42}
    
    await client.set(test_key, test_value, ttl=60)
    result = await client.get(test_key)
    
    assert result is not None
    assert result.get("data") == "smoke_test_value"
    assert result.get("number") == 42
    
    await client.delete(test_key)


@pytest.mark.asyncio
async def test_cache_delete():
    """Проверка удаления из кэша."""
    client = await TarantoolClient.get_instance()
    
    test_key = "smoke_test_delete"
    await client.set(test_key, {"test": True}, ttl=60)
    
    await client.delete(test_key)
    
    result = await client.get(test_key)
    assert result is None


@pytest.mark.asyncio
async def test_persistent_set_and_get():
    """Проверка операций с persistent storage."""
    client = await TarantoolClient.get_instance()
    
    test_key = "smoke_persistent_key"
    test_value = {"persistent": True, "data": "test"}
    
    await client.set_persistent(test_key, test_value)
    result = await client.get_persistent(test_key)
    
    assert result is not None
    assert result.get("persistent") is True
    
    await client.delete_persistent(test_key)


@pytest.mark.asyncio
async def test_cache_metrics():
    """Проверка получения метрик кэша."""
    client = await TarantoolClient.get_instance()
    
    await client.set("metrics_test", {"test": True}, ttl=60)
    await client.get("metrics_test")
    
    stats = await client.get_cache_stats()
    
    assert "hits" in stats or "hit_rate_percent" in stats
    
    await client.delete("metrics_test")


@pytest.mark.asyncio
async def test_list_threads():
    """Проверка получения списка threads."""
    client = await TarantoolClient.get_instance()
    
    threads = await client.list_threads(limit=10)
    
    assert isinstance(threads, list)


@pytest.mark.asyncio
async def test_cache_size():
    """Проверка получения размера кэша."""
    client = await TarantoolClient.get_instance()
    
    size = client.get_cache_size()
    
    assert isinstance(size, int)
    assert size >= 0


@pytest.mark.asyncio
async def test_cache_entries():
    """Проверка получения записей кэша."""
    client = await TarantoolClient.get_instance()
    
    await client.set("entries_test", {"test": True}, ttl=60)
    
    entries = await client.get_entries(limit=10)
    
    assert isinstance(entries, list)
    
    await client.delete("entries_test")


@pytest.mark.asyncio
async def test_fallback_mode_flag():
    """Проверка флага fallback режима."""
    client = await TarantoolClient.get_instance()
    
    assert hasattr(client, "_fallback_mode")
    assert isinstance(client._fallback_mode, bool)

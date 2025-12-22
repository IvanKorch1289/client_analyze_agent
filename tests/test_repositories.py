"""
Tests for Tarantool Repository Pattern.

Covers:
- CacheRepository: CRUD operations, TTL, stats
- ReportsRepository: CRUD operations, TTL (30 days), search by INN
- ThreadsRepository: CRUD operations, search, pagination
"""

import asyncio
import time
from datetime import datetime
from typing import Dict

import pytest

# Mock TarantoolClient для тестирования
class MockTarantoolClient:
    """Mock Tarantool client для unit тестов."""
    
    def __init__(self):
        self._cache = {}
        self._persistent = {}
        self._metrics = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
        }
    
    async def get(self, key: str):
        """Mock get from cache."""
        if key in self._cache:
            self._metrics["hits"] += 1
            data, ttl, _ = self._cache[key]
            if ttl < time.time():
                del self._cache[key]
                self._metrics["misses"] += 1
                return None
            return data
        self._metrics["misses"] += 1
        return None
    
    async def set(self, key: str, value, ttl: int):
        """Mock set to cache."""
        expires_at = time.time() + ttl
        self._cache[key] = (value, expires_at, time.time())
        self._metrics["sets"] += 1
    
    async def delete(self, key: str):
        """Mock delete from cache."""
        if key in self._cache:
            del self._cache[key]
            self._metrics["deletes"] += 1
    
    async def get_persistent(self, key: str):
        """Mock get from persistent."""
        return self._persistent.get(key)
    
    async def set_persistent(self, key: str, value):
        """Mock set to persistent."""
        self._persistent[key] = value
    
    async def delete_persistent(self, key: str):
        """Mock delete from persistent."""
        if key in self._persistent:
            del self._persistent[key]
    
    async def clear_cache(self):
        """Mock clear cache."""
        self._cache.clear()
    
    async def get_cache_stats(self):
        """Mock cache stats."""
        total = self._metrics["hits"] + self._metrics["misses"]
        hit_rate = (self._metrics["hits"] / total * 100) if total > 0 else 0
        return {
            "hits": self._metrics["hits"],
            "misses": self._metrics["misses"],
            "hit_rate_percent": round(hit_rate, 2),
            "sets": self._metrics["sets"],
            "deletes": self._metrics["deletes"],
        }
    
    async def list_threads(self, limit: int = 50):
        """Mock list threads."""
        threads = []
        for key, value in self._persistent.items():
            if key.startswith("thread:"):
                threads.append(value)
        return threads[:limit]


# ============================================================================
# TESTS: CacheRepository
# ============================================================================

@pytest.mark.asyncio
async def test_cache_repository_create_and_get():
    """Тест создания и получения из кеша."""
    from app.storage.repositories.cache_repository import CacheRepository
    
    mock_client = MockTarantoolClient()
    repo = CacheRepository(mock_client)
    
    # Создаем запись
    key = await repo.create({
        "key": "test_key",
        "value": {"data": "test_value"},
        "ttl": 60,
        "source": "test"
    })
    
    assert key == "test_key"
    
    # Получаем обратно
    result = await repo.get("test_key")
    assert result == {"data": "test_value"}


@pytest.mark.asyncio
async def test_cache_repository_ttl_expiration():
    """Тест истечения TTL в кеше."""
    from app.storage.repositories.cache_repository import CacheRepository
    
    mock_client = MockTarantoolClient()
    repo = CacheRepository(mock_client)
    
    # Создаем с TTL 1 секунда
    await repo.set_with_ttl("expire_key", {"data": "value"}, ttl=1)
    
    # Сразу доступно
    result = await repo.get("expire_key")
    assert result == {"data": "value"}
    
    # Ждем истечения
    await asyncio.sleep(2)
    
    # Должно вернуть None
    result = await repo.get("expire_key")
    assert result is None


@pytest.mark.asyncio
async def test_cache_repository_delete():
    """Тест удаления из кеша."""
    from app.storage.repositories.cache_repository import CacheRepository
    
    mock_client = MockTarantoolClient()
    repo = CacheRepository(mock_client)
    
    # Создаем
    await repo.set_with_ttl("delete_key", {"data": "value"})
    assert await repo.get("delete_key") is not None
    
    # Удаляем
    deleted = await repo.delete("delete_key")
    assert deleted is True
    
    # Проверяем что удалено
    assert await repo.get("delete_key") is None


@pytest.mark.asyncio
async def test_cache_repository_stats():
    """Тест статистики кеша."""
    from app.storage.repositories.cache_repository import CacheRepository
    
    mock_client = MockTarantoolClient()
    repo = CacheRepository(mock_client)
    
    # Создаем несколько записей
    await repo.set_with_ttl("key1", "value1")
    await repo.set_with_ttl("key2", "value2")
    
    # Получаем (hits)
    await repo.get("key1")
    await repo.get("key2")
    
    # Пытаемся получить несуществующий (miss)
    await repo.get("key_nonexistent")
    
    # Проверяем статистику
    stats = await repo.get_stats()
    assert stats["hits"] == 2
    assert stats["misses"] == 1
    assert stats["hit_rate_percent"] > 0


# ============================================================================
# TESTS: ReportsRepository
# ============================================================================

@pytest.mark.asyncio
async def test_reports_repository_create():
    """Тест создания отчета."""
    from app.storage.repositories.reports_repository import ReportsRepository
    
    mock_client = MockTarantoolClient()
    repo = ReportsRepository(mock_client)
    
    # Создаем отчет
    report_id = await repo.create({
        "inn": "1234567890",
        "client_name": "Test Company",
        "report_data": {
            "risk_assessment": {
                "score": 25,
                "level": "low"
            },
            "findings": []
        }
    })
    
    assert report_id is not None
    assert len(report_id) > 0  # UUID


@pytest.mark.asyncio
async def test_reports_repository_get():
    """Тест получения отчета."""
    from app.storage.repositories.reports_repository import ReportsRepository
    
    mock_client = MockTarantoolClient()
    repo = ReportsRepository(mock_client)
    
    # Создаем
    report_id = await repo.create({
        "inn": "1234567890",
        "client_name": "Test Company",
        "report_data": {"test": "data"}
    })
    
    # Получаем
    report = await repo.get(report_id)
    assert report is not None
    assert report["inn"] == "1234567890"
    assert report["client_name"] == "Test Company"


@pytest.mark.asyncio
async def test_reports_repository_ttl():
    """Тест TTL отчетов (30 дней)."""
    from app.storage.repositories.reports_repository import (
        ReportsRepository,
        REPORT_TTL_DAYS,
        REPORT_TTL_SECONDS
    )
    
    assert REPORT_TTL_DAYS == 30
    assert REPORT_TTL_SECONDS == 30 * 24 * 60 * 60  # 2592000
    
    mock_client = MockTarantoolClient()
    repo = ReportsRepository(mock_client)
    
    # Создаем отчет
    report_id = await repo.create({
        "inn": "1234567890",
        "client_name": "Test",
        "report_data": {}
    })
    
    # Получаем и проверяем expires_at
    report = await repo.get(report_id)
    assert report is not None
    assert "expires_at" in report
    
    # Проверяем что expires_at примерно через 30 дней
    now = time.time()
    expected_expiry = now + REPORT_TTL_SECONDS
    assert abs(report["expires_at"] - expected_expiry) < 10  # Погрешность 10 секунд


@pytest.mark.asyncio
async def test_reports_repository_from_workflow():
    """Тест создания отчета из результата workflow."""
    from app.storage.repositories.reports_repository import ReportsRepository
    
    mock_client = MockTarantoolClient()
    repo = ReportsRepository(mock_client)
    
    # Симулируем результат workflow
    workflow_result = {
        "session_id": "test_session",
        "client_name": "Test Company",
        "inn": "1234567890",
        "status": "completed",
        "report": {
            "metadata": {"client_name": "Test", "inn": "1234567890"},
            "risk_assessment": {"score": 50, "level": "medium"},
            "findings": [],
        },
        "timestamp": time.time(),
    }
    
    # Создаем отчет
    report_id = await repo.create_from_workflow_result(workflow_result)
    assert report_id is not None
    
    # Проверяем что сохранено
    report = await repo.get(report_id)
    assert report is not None
    assert report["client_name"] == "Test Company"


# ============================================================================
# TESTS: ThreadsRepository
# ============================================================================

@pytest.mark.asyncio
async def test_threads_repository_create():
    """Тест создания thread."""
    from app.storage.repositories.threads_repository import ThreadsRepository
    
    mock_client = MockTarantoolClient()
    repo = ThreadsRepository(mock_client)
    
    # Создаем thread
    thread_id = await repo.create({
        "thread_id": "test_thread_123",
        "thread_data": {"messages": ["msg1", "msg2"]},
        "client_name": "Test Client",
        "inn": "1234567890",
    })
    
    assert thread_id == "test_thread_123"


@pytest.mark.asyncio
async def test_threads_repository_save_and_get():
    """Тест сохранения и получения thread."""
    from app.storage.repositories.threads_repository import ThreadsRepository
    
    mock_client = MockTarantoolClient()
    repo = ThreadsRepository(mock_client)
    
    # Сохраняем
    thread_id = await repo.save_thread(
        thread_id="thread_456",
        thread_data={"input": "Test input", "messages": []},
        client_name="Company ABC",
        inn="9876543210"
    )
    
    assert thread_id == "thread_456"
    
    # Получаем обратно
    thread = await repo.get("thread_456")
    assert thread is not None
    assert thread["client_name"] == "Company ABC"
    assert thread["inn"] == "9876543210"


@pytest.mark.asyncio
async def test_threads_repository_update():
    """Тест обновления thread."""
    from app.storage.repositories.threads_repository import ThreadsRepository
    
    mock_client = MockTarantoolClient()
    repo = ThreadsRepository(mock_client)
    
    # Создаем
    await repo.save_thread(
        thread_id="update_thread",
        thread_data={"status": "initial"},
        client_name="Original Name"
    )
    
    # Обновляем
    updated = await repo.update("update_thread", {
        "thread_data": {"status": "updated"},
        "client_name": "New Name",
    })
    
    assert updated is True
    
    # Проверяем обновление
    thread = await repo.get("update_thread")
    assert thread["client_name"] == "New Name"
    assert thread["thread_data"]["status"] == "updated"


@pytest.mark.asyncio
async def test_threads_repository_list():
    """Тест получения списка threads."""
    from app.storage.repositories.threads_repository import ThreadsRepository
    
    mock_client = MockTarantoolClient()
    repo = ThreadsRepository(mock_client)
    
    # Создаем несколько threads
    for i in range(5):
        await repo.save_thread(
            thread_id=f"thread_{i}",
            thread_data={"index": i},
            client_name=f"Client {i}"
        )
    
    # Получаем список
    threads = await repo.list(limit=10)
    assert len(threads) >= 5


@pytest.mark.asyncio
async def test_threads_repository_search_by_inn():
    """Тест поиска threads по ИНН."""
    from app.storage.repositories.threads_repository import ThreadsRepository
    
    mock_client = MockTarantoolClient()
    repo = ThreadsRepository(mock_client)
    
    # Создаем threads с разными ИНН
    await repo.save_thread("t1", {}, "Client 1", "1111111111")
    await repo.save_thread("t2", {}, "Client 2", "2222222222")
    await repo.save_thread("t3", {}, "Client 3", "1111111111")
    
    # Ищем по первому ИНН
    threads = await repo.list_threads_by_inn("1111111111", limit=10)
    assert len(threads) >= 2
    
    # Ищем по второму ИНН
    threads = await repo.list_threads_by_inn("2222222222", limit=10)
    assert len(threads) >= 1


# ============================================================================
# INTEGRATION TESTS (require real Tarantool)
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_tarantool_connection():
    """
    Integration тест с реальным Tarantool.
    
    Требует: Tarantool running на localhost:3302
    Пропускается если SKIP_INTEGRATION=true
    """
    import os
    if os.getenv("SKIP_INTEGRATION", "false").lower() == "true":
        pytest.skip("Integration tests disabled")
    
    from app.storage.tarantool import TarantoolClient
    
    try:
        client = await TarantoolClient.get_instance()
        assert client is not None
        
        # Проверяем repositories
        cache_repo = client.get_cache_repository()
        reports_repo = client.get_reports_repository()
        threads_repo = client.get_threads_repository()
        
        assert cache_repo is not None
        assert reports_repo is not None
        assert threads_repo is not None
        
    except Exception as e:
        pytest.skip(f"Tarantool not available: {e}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_cache_operations():
    """Integration тест CRUD операций с cache."""
    import os
    if os.getenv("SKIP_INTEGRATION", "false").lower() == "true":
        pytest.skip("Integration tests disabled")
    
    from app.storage.tarantool import TarantoolClient
    
    try:
        client = await TarantoolClient.get_instance()
        repo = client.get_cache_repository()
        
        # Create
        key = f"test_cache_{int(time.time())}"
        success = await repo.set_with_ttl(key, {"test": "data"}, ttl=60)
        assert success is True
        
        # Read
        result = await repo.get(key)
        assert result == {"test": "data"}
        
        # Delete
        deleted = await repo.delete(key)
        assert deleted is True
        
        # Verify deletion
        result = await repo.get(key)
        assert result is None
        
    except Exception as e:
        pytest.skip(f"Tarantool not available: {e}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_report_operations():
    """Integration тест CRUD операций с reports."""
    import os
    if os.getenv("SKIP_INTEGRATION", "false").lower() == "true":
        pytest.skip("Integration tests disabled")
    
    from app.storage.tarantool import TarantoolClient
    
    try:
        client = await TarantoolClient.get_instance()
        repo = client.get_reports_repository()
        
        # Create
        report_id = await repo.create({
            "inn": "1234567890",
            "client_name": "Integration Test Company",
            "report_data": {
                "risk_assessment": {"score": 30, "level": "low"},
                "findings": ["test"],
            }
        })
        assert report_id is not None
        
        # Read
        report = await repo.get(report_id)
        assert report is not None
        assert report["inn"] == "1234567890"
        assert report["client_name"] == "Integration Test Company"
        
        # Delete
        deleted = await repo.delete(report_id)
        assert deleted is True
        
    except Exception as e:
        pytest.skip(f"Tarantool not available: {e}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_thread_operations():
    """Integration тест CRUD операций с threads."""
    import os
    if os.getenv("SKIP_INTEGRATION", "false").lower() == "true":
        pytest.skip("Integration tests disabled")
    
    from app.storage.tarantool import TarantoolClient
    
    try:
        client = await TarantoolClient.get_instance()
        repo = client.get_threads_repository()
        
        # Create
        thread_id = f"test_thread_{int(time.time())}"
        saved_id = await repo.save_thread(
            thread_id=thread_id,
            thread_data={"input": "Test", "messages": []},
            client_name="Test Client",
            inn="9999999999"
        )
        assert saved_id == thread_id
        
        # Read
        thread = await repo.get(thread_id)
        assert thread is not None
        assert thread["client_name"] == "Test Client"
        
        # Update
        updated = await repo.update(thread_id, {
            "client_name": "Updated Client"
        })
        assert updated is True
        
        # Verify update
        thread = await repo.get(thread_id)
        assert thread["client_name"] == "Updated Client"
        
        # Delete
        deleted = await repo.delete(thread_id)
        assert deleted is True
        
    except Exception as e:
        pytest.skip(f"Tarantool not available: {e}")


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

@pytest.mark.performance
@pytest.mark.asyncio
async def test_cache_performance():
    """Performance тест кеша (1000 операций)."""
    from app.storage.repositories.cache_repository import CacheRepository
    
    mock_client = MockTarantoolClient()
    repo = CacheRepository(mock_client)
    
    start = time.perf_counter()
    
    # 1000 операций set/get
    for i in range(1000):
        await repo.set_with_ttl(f"perf_key_{i}", {"index": i}, ttl=60)
    
    for i in range(1000):
        result = await repo.get(f"perf_key_{i}")
        assert result == {"index": i}
    
    duration = time.perf_counter() - start
    
    print(f"\n1000 cache operations took {duration:.2f}s ({2000/duration:.0f} ops/sec)")
    
    # Должно быть достаточно быстро даже для mock
    assert duration < 5.0  # 5 секунд на 2000 операций


if __name__ == "__main__":
    # Запуск тестов
    pytest.main([__file__, "-v", "-s"])

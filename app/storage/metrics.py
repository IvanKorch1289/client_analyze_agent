"""
Cache metrics for Tarantool storage.

Provides tracking for hits, misses, latency, and compression stats.
"""

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class CacheMetrics:
    """
    Tracks cache performance metrics.

    Attributes:
        hits: Number of cache hits
        misses: Number of cache misses
        sets: Number of set operations
        deletes: Number of delete operations
        batch_operations: Number of batch operations
        compressed_saves: Number of compressed saves
        bytes_saved_by_compression: Total bytes saved by compression
        total_get_time_ms: Total time spent on get operations (ms)
        total_set_time_ms: Total time spent on set operations (ms)
    """

    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    batch_operations: int = 0
    compressed_saves: int = 0
    bytes_saved_by_compression: int = 0
    total_get_time_ms: float = 0.0
    total_set_time_ms: float = 0.0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate as percentage."""
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0

    @property
    def avg_get_time_ms(self) -> float:
        """Calculate average get operation time in milliseconds."""
        total = self.hits + self.misses
        return (self.total_get_time_ms / total) if total > 0 else 0.0

    @property
    def avg_set_time_ms(self) -> float:
        """Calculate average set operation time in milliseconds."""
        return (self.total_set_time_ms / self.sets) if self.sets > 0 else 0.0

    @property
    def total_operations(self) -> int:
        """Total number of operations."""
        return self.hits + self.misses + self.sets + self.deletes

    def record_hit(self, elapsed_ms: float = 0.0) -> None:
        """Record a cache hit."""
        self.hits += 1
        self.total_get_time_ms += elapsed_ms

    def record_miss(self, elapsed_ms: float = 0.0) -> None:
        """Record a cache miss."""
        self.misses += 1
        self.total_get_time_ms += elapsed_ms

    def record_set(self, elapsed_ms: float = 0.0) -> None:
        """Record a set operation."""
        self.sets += 1
        self.total_set_time_ms += elapsed_ms

    def record_delete(self, count: int = 1) -> None:
        """Record delete operation(s)."""
        self.deletes += count

    def record_batch(self) -> None:
        """Record a batch operation."""
        self.batch_operations += 1

    def record_compression(self, bytes_saved: int) -> None:
        """Record compression savings."""
        self.compressed_saves += 1
        self.bytes_saved_by_compression += bytes_saved

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for JSON serialization."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate_percent": round(self.hit_rate, 2),
            "sets": self.sets,
            "deletes": self.deletes,
            "batch_operations": self.batch_operations,
            "compressed_saves": self.compressed_saves,
            "bytes_saved_by_compression": self.bytes_saved_by_compression,
            "avg_get_time_ms": round(self.avg_get_time_ms, 2),
            "avg_set_time_ms": round(self.avg_set_time_ms, 2),
            "total_operations": self.total_operations,
        }

    def reset(self) -> None:
        """Reset all metrics to zero."""
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.deletes = 0
        self.batch_operations = 0
        self.compressed_saves = 0
        self.bytes_saved_by_compression = 0
        self.total_get_time_ms = 0.0
        self.total_set_time_ms = 0.0

    def merge(self, other: "CacheMetrics") -> None:
        """Merge another metrics instance into this one."""
        self.hits += other.hits
        self.misses += other.misses
        self.sets += other.sets
        self.deletes += other.deletes
        self.batch_operations += other.batch_operations
        self.compressed_saves += other.compressed_saves
        self.bytes_saved_by_compression += other.bytes_saved_by_compression
        self.total_get_time_ms += other.total_get_time_ms
        self.total_set_time_ms += other.total_set_time_ms


@dataclass
class SourceMetrics:
    """
    Tracks metrics per data source (DaData, Casebook, etc.).

    Useful for monitoring which sources are slow or failing.
    """

    source_name: str
    requests: int = 0
    successes: int = 0
    failures: int = 0
    total_time_ms: float = 0.0
    cache_hits: int = 0

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        return (self.successes / self.requests * 100) if self.requests > 0 else 0.0

    @property
    def avg_time_ms(self) -> float:
        """Calculate average request time in milliseconds."""
        return (self.total_time_ms / self.requests) if self.requests > 0 else 0.0

    def record_request(self, success: bool, elapsed_ms: float, from_cache: bool = False) -> None:
        """Record a request to this source."""
        self.requests += 1
        self.total_time_ms += elapsed_ms
        if success:
            self.successes += 1
        else:
            self.failures += 1
        if from_cache:
            self.cache_hits += 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source": self.source_name,
            "requests": self.requests,
            "successes": self.successes,
            "failures": self.failures,
            "success_rate_percent": round(self.success_rate, 2),
            "avg_time_ms": round(self.avg_time_ms, 2),
            "cache_hits": self.cache_hits,
        }


class MetricsRegistry:
    """
    Registry for managing multiple metric instances.

    Provides global access to cache and source metrics.
    """

    _instance: "MetricsRegistry" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache_metrics = CacheMetrics()
            cls._instance._source_metrics: Dict[str, SourceMetrics] = {}
        return cls._instance

    @property
    def cache(self) -> CacheMetrics:
        """Get cache metrics."""
        return self._cache_metrics

    def get_source(self, name: str) -> SourceMetrics:
        """Get or create metrics for a specific source."""
        if name not in self._source_metrics:
            self._source_metrics[name] = SourceMetrics(source_name=name)
        return self._source_metrics[name]

    def all_sources(self) -> Dict[str, SourceMetrics]:
        """Get all source metrics."""
        return self._source_metrics.copy()

    def to_dict(self) -> Dict[str, Any]:
        """Export all metrics as dictionary."""
        return {
            "cache": self._cache_metrics.to_dict(),
            "sources": {name: m.to_dict() for name, m in self._source_metrics.items()},
        }

    def reset_all(self) -> None:
        """Reset all metrics."""
        self._cache_metrics.reset()
        self._source_metrics.clear()

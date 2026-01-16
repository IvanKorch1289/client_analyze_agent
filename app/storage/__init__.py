"""
Storage module for Tarantool cache and repositories.

This module provides:
- TarantoolClient: Main async client for cache operations
- ConnectionManager: Connection lifecycle management
- CompressionHandler: Data compression utilities
- CacheMetrics: Performance tracking
- Repository classes for different data types
"""

from app.storage.compression import CompressionConfig, CompressionHandler
from app.storage.connection import ConnectionManager, get_executor
from app.storage.metrics import CacheMetrics, MetricsRegistry, SourceMetrics
from app.storage.tarantool import TarantoolClient, save_thread_to_tarantool

__all__ = [
    # Main client
    "TarantoolClient",
    "save_thread_to_tarantool",
    # Connection
    "ConnectionManager",
    "get_executor",
    # Compression
    "CompressionHandler",
    "CompressionConfig",
    # Metrics
    "CacheMetrics",
    "SourceMetrics",
    "MetricsRegistry",
]

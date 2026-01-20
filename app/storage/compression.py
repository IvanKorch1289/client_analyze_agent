"""
Compression utilities for Tarantool cache storage.

Provides gzip compression/decompression with configurable thresholds.
"""

import gzip
from dataclasses import dataclass
from typing import Optional

COMPRESSION_MARKER = b"\x1f\x8b"


@dataclass
class CompressionConfig:
    """Configuration for compression behavior."""

    threshold: int = 1024
    level: int = 6


class CompressionHandler:
    """
    Handles compression and decompression of cached data.

    Uses gzip with configurable compression level.
    Only compresses data above threshold size.
    """

    def __init__(self, config: Optional[CompressionConfig] = None):
        self._config = config or CompressionConfig()
        self._compressed_count: int = 0
        self._bytes_saved: int = 0

    @property
    def threshold(self) -> int:
        return self._config.threshold

    @property
    def level(self) -> int:
        return self._config.level

    @property
    def stats(self) -> dict:
        return {
            "compressed_saves": self._compressed_count,
            "bytes_saved_by_compression": self._bytes_saved,
        }

    def reset_stats(self) -> None:
        self._compressed_count = 0
        self._bytes_saved = 0

    def compress(self, data: bytes) -> bytes:
        """
        Compress data if it exceeds the threshold.

        Args:
            data: Raw bytes to compress

        Returns:
            Compressed bytes if beneficial, otherwise original data
        """
        if not data or len(data) < self._config.threshold:
            return data

        compressed = gzip.compress(data, compresslevel=self._config.level)

        if len(compressed) < len(data):
            self._compressed_count += 1
            self._bytes_saved += len(data) - len(compressed)
            return compressed

        return data

    def decompress(self, data: bytes) -> bytes:
        """
        Decompress data if it has the gzip marker.

        Args:
            data: Potentially compressed bytes

        Returns:
            Decompressed bytes
        """
        if data and len(data) >= 2 and data[:2] == COMPRESSION_MARKER:
            return gzip.decompress(data)
        return data

    def is_compressed(self, data: bytes) -> bool:
        """Check if data has gzip compression marker."""
        return bool(data and len(data) >= 2 and data[:2] == COMPRESSION_MARKER)

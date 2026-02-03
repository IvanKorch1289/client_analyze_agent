"""
Base collector class for data sources.

Provides common interface and utilities for all collectors.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.shared.toolkit.logging import logger


@dataclass
class CollectorResult:
    """
    Standardized result from any collector.

    Attributes:
        source: Name of the data source
        success: Whether the collection succeeded
        data: Collected data (format varies by source)
        error: Error message if failed
        elapsed_ms: Time taken in milliseconds
        intent_id: Optional intent identifier for web searches
        metadata: Additional metadata
    """

    source: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    elapsed_ms: float = 0.0
    intent_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        result = {
            "source": self.source,
            "success": self.success,
            "error": self.error,
            "elapsed_ms": round(self.elapsed_ms, 2),
        }
        if self.data is not None:
            result["data"] = self.data
        if self.intent_id:
            result["intent_id"] = self.intent_id
        if self.metadata:
            result["metadata"] = self.metadata
        return result


class BaseCollector(ABC):
    """
    Abstract base class for data collectors.

    Provides:
    - Common error handling
    - Timeout management
    - Logging utilities
    - Metrics tracking
    """

    source_name: str = "base"
    default_timeout: int = 30

    def __init__(self, timeout: Optional[int] = None):
        self._timeout = timeout or self.default_timeout
        self._request_count = 0
        self._success_count = 0
        self._total_time_ms = 0.0

    @property
    def stats(self) -> Dict[str, Any]:
        """Get collector statistics."""
        return {
            "source": self.source_name,
            "requests": self._request_count,
            "successes": self._success_count,
            "success_rate": (self._success_count / self._request_count * 100 if self._request_count > 0 else 0),
            "avg_time_ms": (self._total_time_ms / self._request_count if self._request_count > 0 else 0),
        }

    @abstractmethod
    async def _collect(self, **kwargs) -> CollectorResult:
        """
        Internal collection method to be implemented by subclasses.

        Args:
            **kwargs: Source-specific parameters

        Returns:
            CollectorResult with collected data
        """
        pass

    async def collect(self, **kwargs) -> CollectorResult:
        """
        Main collection method with error handling and timing.

        Args:
            **kwargs: Source-specific parameters

        Returns:
            CollectorResult with collected data or error
        """
        self._request_count += 1
        start_time = time.perf_counter()

        try:
            result = await asyncio.wait_for(
                self._collect(**kwargs),
                timeout=self._timeout,
            )
            result.elapsed_ms = (time.perf_counter() - start_time) * 1000

            if result.success:
                self._success_count += 1

            self._total_time_ms += result.elapsed_ms

            logger.info(
                f"{self.source_name}: collection completed",
                component="collector",
                success=result.success,
                elapsed_ms=round(result.elapsed_ms, 2),
            )

            return result

        except asyncio.TimeoutError:
            elapsed = (time.perf_counter() - start_time) * 1000
            self._total_time_ms += elapsed

            logger.warning(
                f"{self.source_name}: timeout after {self._timeout}s",
                component="collector",
            )

            return CollectorResult(
                source=self.source_name,
                success=False,
                error=f"Timeout after {self._timeout}s",
                elapsed_ms=elapsed,
            )

        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            self._total_time_ms += elapsed

            logger.error(
                f"{self.source_name}: collection failed: {e}",
                component="collector",
            )

            return CollectorResult(
                source=self.source_name,
                success=False,
                error=str(e),
                elapsed_ms=elapsed,
            )

    def is_configured(self) -> bool:
        """Check if collector is properly configured."""
        return True


class CompositeCollector:
    """
    Runs multiple collectors in parallel.

    Useful for gathering data from multiple sources simultaneously.
    """

    def __init__(self, collectors: List[BaseCollector]):
        self._collectors = collectors

    async def collect_all(self, **kwargs) -> List[CollectorResult]:
        """
        Run all collectors in parallel.

        Args:
            **kwargs: Parameters passed to all collectors

        Returns:
            List of CollectorResult from all collectors
        """
        tasks = [collector.collect(**kwargs) for collector in self._collectors]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to CollectorResult
        processed = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed.append(
                    CollectorResult(
                        source=self._collectors[i].source_name,
                        success=False,
                        error=str(result),
                    )
                )
            else:
                processed.append(result)

        return processed

    def get_stats(self) -> Dict[str, Any]:
        """Get combined statistics from all collectors."""
        return {collector.source_name: collector.stats for collector in self._collectors}

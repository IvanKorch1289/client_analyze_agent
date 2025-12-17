import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.advanced_funcs.logging_client import logger

logging.getLogger("httpx").setLevel(logging.WARNING)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    success_threshold: int = 2
    timeout: float = 30.0
    excluded_exceptions: Set[type] = field(default_factory=set)


@dataclass
class TimeoutConfig:
    connect: float = 5.0
    read: float = 30.0
    write: float = 10.0
    pool: float = 5.0

    def to_httpx_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.connect,
            read=self.read,
            write=self.write,
            pool=self.pool,
        )


@dataclass
class RetryConfig:
    max_attempts: int = 3
    min_wait: float = 0.5
    max_wait: float = 10.0
    exponential_base: float = 2.0


@dataclass
class RequestMetrics:
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    retried_requests: int = 0
    circuit_breaker_rejections: int = 0
    total_latency_ms: float = 0.0
    last_request_time: Optional[float] = None

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests * 100

    @property
    def avg_latency_ms(self) -> float:
        if self.successful_requests == 0:
            return 0.0
        return self.total_latency_ms / self.successful_requests

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "retried_requests": self.retried_requests,
            "circuit_breaker_rejections": self.circuit_breaker_rejections,
            "success_rate_percent": round(self.success_rate, 2),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "last_request_time": self.last_request_time,
        }


class CircuitBreaker:
    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def is_available(self) -> bool:
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.OPEN:
            if self._last_failure_time is None:
                return False
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self.config.timeout:
                return True
            return False
        return True

    async def record_success(self):
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    logger.info(
                        f"Circuit breaker '{self.name}' closed after successful requests",
                        component="circuit_breaker",
                    )
            elif self._state == CircuitState.CLOSED:
                self._failure_count = max(0, self._failure_count - 1)

    async def record_failure(self, exception: Optional[Exception] = None):
        if exception and type(exception) in self.config.excluded_exceptions:
            return

        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._success_count = 0
                logger.warning(
                    f"Circuit breaker '{self.name}' opened (failure in half-open state)",
                    component="circuit_breaker",
                )
            elif (
                self._state == CircuitState.CLOSED
                and self._failure_count >= self.config.failure_threshold
            ):
                self._state = CircuitState.OPEN
                logger.warning(
                    f"Circuit breaker '{self.name}' opened after {self._failure_count} failures",
                    component="circuit_breaker",
                )

    async def check_state(self) -> bool:
        async with self._lock:
            if self._state == CircuitState.OPEN:
                if self._last_failure_time is None:
                    return False
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.config.timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                    logger.info(
                        f"Circuit breaker '{self.name}' entering half-open state",
                        component="circuit_breaker",
                    )
                    return True
                return False
            return True

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "is_available": self.is_available,
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "success_threshold": self.config.success_threshold,
                "timeout": self.config.timeout,
            },
        }


class CircuitBreakerOpenError(Exception):
    def __init__(self, circuit_name: str):
        self.circuit_name = circuit_name
        super().__init__(f"Circuit breaker '{circuit_name}' is open")


class AsyncHttpClient:
    _instance: Optional["AsyncHttpClient"] = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __new__(cls) -> "AsyncHttpClient":
        return super().__new__(cls)

    @classmethod
    async def get_instance(cls) -> "AsyncHttpClient":
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance.__init_once()
                    await instance._initialize()
                    cls._instance = instance
        return cls._instance

    def __init__(self):
        raise RuntimeError(
            f"Нельзя создавать экземпляр {self.__class__.__name__} напрямую. "
            f"Используйте {self.__class__.__name__}.get_instance()"
        )

    def __init_once(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._initialized: bool = False
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._metrics: Dict[str, RequestMetrics] = {}
        self._default_timeout = TimeoutConfig()
        self._default_retry = RetryConfig()
        self._service_configs: Dict[str, Dict[str, Any]] = {
            "tavily": {
                "timeout": TimeoutConfig(connect=10.0, read=120.0, write=15.0, pool=10.0),
                "retry": RetryConfig(max_attempts=3, min_wait=1.0, max_wait=30.0),
                "circuit_breaker": CircuitBreakerConfig(
                    failure_threshold=5, success_threshold=2, timeout=120.0
                ),
            },
            "perplexity": {
                "timeout": TimeoutConfig(connect=10.0, read=150.0, write=15.0, pool=10.0),
                "retry": RetryConfig(max_attempts=3, min_wait=1.0, max_wait=30.0),
                "circuit_breaker": CircuitBreakerConfig(
                    failure_threshold=5, success_threshold=2, timeout=120.0
                ),
            },
            "dadata": {
                "timeout": TimeoutConfig(connect=5.0, read=30.0, write=10.0, pool=5.0),
                "retry": RetryConfig(max_attempts=2, min_wait=0.5, max_wait=5.0),
                "circuit_breaker": CircuitBreakerConfig(
                    failure_threshold=3, success_threshold=1, timeout=30.0
                ),
            },
            "infosphere": {
                "timeout": TimeoutConfig(connect=5.0, read=45.0, write=10.0, pool=5.0),
                "retry": RetryConfig(max_attempts=2, min_wait=0.5, max_wait=5.0),
                "circuit_breaker": CircuitBreakerConfig(
                    failure_threshold=3, success_threshold=1, timeout=30.0
                ),
            },
            "casebook": {
                "timeout": TimeoutConfig(connect=5.0, read=30.0, write=10.0, pool=5.0),
                "retry": RetryConfig(max_attempts=2, min_wait=0.5, max_wait=5.0),
                "circuit_breaker": CircuitBreakerConfig(
                    failure_threshold=3, success_threshold=1, timeout=30.0
                ),
            },
        }

    async def _initialize(self):
        if self._initialized:
            return

        transport = httpx.AsyncHTTPTransport(retries=0)
        self._client = httpx.AsyncClient(
            http2=True,
            limits=httpx.Limits(
                max_connections=50,
                max_keepalive_connections=20,
            ),
            timeout=self._default_timeout.to_httpx_timeout(),
            event_hooks={
                "request": [self._on_request],
                "response": [self._on_response],
            },
            transport=transport,
        )
        self._initialized = True

    async def _on_request(self, request: httpx.Request):
        request.extensions["start_time"] = asyncio.get_event_loop().time()
        logger.log_request(request)

    async def _on_response(self, response: httpx.Response):
        start_time = response.request.extensions.get("start_time", None)
        duration = asyncio.get_event_loop().time() - start_time if start_time else 0.0
        logger.log_response(response, duration=duration)

    def _get_circuit_breaker(self, service: str) -> CircuitBreaker:
        if service not in self._circuit_breakers:
            config = self._service_configs.get(service, {}).get(
                "circuit_breaker", CircuitBreakerConfig()
            )
            self._circuit_breakers[service] = CircuitBreaker(service, config)
        return self._circuit_breakers[service]

    def _get_metrics(self, service: str) -> RequestMetrics:
        if service not in self._metrics:
            self._metrics[service] = RequestMetrics()
        return self._metrics[service]

    def _detect_service(self, url: str) -> str:
        url_lower = url.lower()
        if "tavily" in url_lower:
            return "tavily"
        elif "perplexity" in url_lower:
            return "perplexity"
        elif "dadata" in url_lower:
            return "dadata"
        elif "i-sphere" in url_lower or "infosphere" in url_lower:
            return "infosphere"
        elif "casebook" in url_lower:
            return "casebook"
        return "default"

    async def request_with_resilience(
        self,
        method: str,
        url: str,
        service: Optional[str] = None,
        timeout_config: Optional[TimeoutConfig] = None,
        retry_config: Optional[RetryConfig] = None,
        use_circuit_breaker: bool = True,
        **kwargs,
    ) -> httpx.Response:
        if not self._client:
            raise RuntimeError("HTTP-клиент не инициализирован.")

        detected_service = service or self._detect_service(url)
        service_config = self._service_configs.get(detected_service, {})
        timeout = timeout_config or service_config.get("timeout", self._default_timeout)
        retry = retry_config or service_config.get("retry", self._default_retry)
        metrics = self._get_metrics(detected_service)

        circuit_breaker: Optional[CircuitBreaker] = None
        if use_circuit_breaker:
            circuit_breaker = self._get_circuit_breaker(detected_service)
            is_available = await circuit_breaker.check_state()
            if not is_available:
                metrics.circuit_breaker_rejections += 1
                raise CircuitBreakerOpenError(detected_service)

        metrics.total_requests += 1
        metrics.last_request_time = time.time()
        start_time = time.time()
        last_exception: Optional[Exception] = None

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(retry.max_attempts),
                wait=wait_exponential(
                    multiplier=retry.min_wait,
                    min=retry.min_wait,
                    max=retry.max_wait,
                    exp_base=retry.exponential_base,
                ),
                retry=retry_if_exception_type(
                    (httpx.RequestError, httpx.TimeoutException, httpx.HTTPStatusError)
                ),
                reraise=True,
            ):
                with attempt:
                    if attempt.retry_state.attempt_number > 1:
                        metrics.retried_requests += 1
                        logger.info(
                            f"Retry attempt {attempt.retry_state.attempt_number} for {detected_service}",
                            component="http_client",
                        )

                    response = await self._client.request(
                        method,
                        url,
                        timeout=timeout.to_httpx_timeout(),
                        **kwargs,
                    )

                    if response.status_code == 429:
                        retry_after = response.headers.get("Retry-After", "5")
                        wait_time = float(retry_after) if retry_after.isdigit() else 5.0
                        logger.warning(
                            f"Rate limited by {detected_service}, waiting {wait_time}s",
                            component="http_client",
                        )
                        await asyncio.sleep(wait_time)
                        raise httpx.HTTPStatusError(
                            "Rate limited", request=response.request, response=response
                        )

                    if 500 <= response.status_code < 600:
                        raise httpx.HTTPStatusError(
                            f"Server error: {response.status_code}",
                            request=response.request,
                            response=response,
                        )

                    response.raise_for_status()

                    elapsed_ms = (time.time() - start_time) * 1000
                    metrics.successful_requests += 1
                    metrics.total_latency_ms += elapsed_ms

                    if circuit_breaker:
                        await circuit_breaker.record_success()

                    return response

        except RetryError as e:
            exc = e.last_attempt.exception()
            last_exception = exc if isinstance(exc, Exception) else None
            metrics.failed_requests += 1
            if circuit_breaker:
                await circuit_breaker.record_failure(last_exception)
            logger.error(
                f"Request to {detected_service} failed after {retry.max_attempts} attempts: {last_exception}",
                component="http_client",
            )
            if last_exception:
                raise last_exception from e
            else:
                raise

        except Exception as e:
            metrics.failed_requests += 1
            if circuit_breaker:
                await circuit_breaker.record_failure(e)
            raise

        raise RuntimeError("Unreachable: request failed without exception")

    async def request(
        self,
        method: str,
        url: str,
        use_resilience: bool = True,
        **kwargs,
    ) -> httpx.Response:
        if use_resilience:
            return await self.request_with_resilience(method, url, **kwargs)

        if not self._client:
            raise RuntimeError("Клиент не инициализирован.")
        return await self._client.request(method, url, **kwargs)

    async def get(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("DELETE", url, **kwargs)

    async def fetch_all_pages(
        self,
        url: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        data_extractor: Optional[Callable[[Dict[str, Any]], List[Any]]] = None,
        page_extractor: Optional[Callable[[Dict[str, Any]], Optional[int]]] = None,
        **kwargs,
    ) -> List[Any]:
        if not self._client:
            raise RuntimeError("Клиент не инициализирован.")

        all_data: List[Any] = []
        params = params or {}
        current_page = params.get("page", 1)
        seen_pages: Set[int] = set()

        def default_data_extractor(data: Dict[str, Any]) -> List[Any]:
            for key in ("data", "results", "items", "entries"):
                if isinstance(data.get(key), list):
                    return data[key]
            return []

        def default_page_extractor(data: Dict[str, Any]) -> Optional[int]:
            return (
                data.get("total_pages")
                or data.get("pagination", {}).get("total_pages")
                or data.get("meta", {}).get("total_pages")
            )

        extract_data = data_extractor or default_data_extractor
        extract_total_pages = page_extractor or default_page_extractor

        while True:
            if current_page in seen_pages:
                logger.warning(
                    f"Обнаружена зацикленная пагинация на странице {current_page}",
                    component="http_client",
                )
                break
            seen_pages.add(current_page)

            request_params = {**params, "page": current_page}

            try:
                response = await self.request(
                    method=method,
                    url=url,
                    params=request_params,
                    **kwargs,
                )
                json_data = response.json()
                page_items = extract_data(json_data)
                all_data.extend(page_items)
                total_pages = extract_total_pages(json_data)

                if total_pages is None:
                    logger.info(
                        f"Пагинация не обнаружена. Останавливаемся после страницы {current_page}.",
                        component="http_client",
                    )
                    break

                if current_page >= total_pages:
                    break

                current_page += 1

            except Exception as e:
                logger.error(
                    f"Ошибка при запросе страницы {current_page}: {str(e)}",
                    component="http_client",
                )
                break

        return all_data

    def get_circuit_breaker_status(
        self, service: Optional[str] = None
    ) -> Dict[str, Any]:
        if service:
            if service in self._circuit_breakers:
                return self._circuit_breakers[service].get_status()
            return {"error": f"No circuit breaker for service: {service}"}

        return {name: cb.get_status() for name, cb in self._circuit_breakers.items()}

    def get_metrics(self, service: Optional[str] = None) -> Dict[str, Any]:
        if service:
            if service in self._metrics:
                return self._metrics[service].to_dict()
            return {"error": f"No metrics for service: {service}"}

        return {name: m.to_dict() for name, m in self._metrics.items()}

    def reset_circuit_breaker(self, service: str) -> bool:
        if service in self._circuit_breakers:
            del self._circuit_breakers[service]
            logger.info(
                f"Circuit breaker '{service}' has been reset",
                component="circuit_breaker",
            )
            return True
        return False

    def reset_metrics(self, service: Optional[str] = None):
        if service:
            if service in self._metrics:
                self._metrics[service] = RequestMetrics()
        else:
            self._metrics.clear()

    async def aclose(self):
        if self._client:
            await self._client.aclose()
            self._client = None
        self._initialized = False

    @classmethod
    async def close_global(cls):
        if cls._instance is not None:
            await cls._instance.aclose()
            cls._instance = None

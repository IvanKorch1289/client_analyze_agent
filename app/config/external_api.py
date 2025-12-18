"""
Настройки подключения к внешним API.

Содержит конфигурацию для:
- DaData (проверка компаний по ИНН)
- Perplexity (AI-powered search)
- Tavily (web search)
- OpenRouter (LLM провайдер)
- Casebook (судебные дела)
- InfoSphere (проверка контрагентов)
"""

from typing import Optional

from pydantic import Field

from app.config.config_loader import BaseSettingsWithLoader


class HttpBaseSettings(BaseSettingsWithLoader):
    """Базовые настройки для HTTP клиентов."""
    
    yaml_group = "http_base"
    vault_path = "secret/data/app/http"
    
    # Таймауты (секунды)
    connect_timeout: float = Field(default=5.0, description="Таймаут подключения")
    read_timeout: float = Field(default=30.0, description="Таймаут чтения")
    write_timeout: float = Field(default=10.0, description="Таймаут записи")
    pool_timeout: float = Field(default=5.0, description="Таймаут пула")
    
    # Retry
    max_retries: int = Field(default=3, description="Максимум повторных попыток")
    retry_backoff_factor: float = Field(default=0.5, description="Фактор экспоненциального отката")
    
    # Connection pooling
    max_connections: int = Field(default=50, description="Максимум соединений")
    max_keepalive_connections: int = Field(default=20, description="Максимум keep-alive соединений")
    
    # HTTP/2
    http2_enabled: bool = Field(default=True, description="Включить HTTP/2")
    
    class Config:
        env_prefix = "HTTP_"


class DadataAPISettings(BaseSettingsWithLoader):
    """Настройки DaData API."""
    
    yaml_group = "dadata"
    vault_path = "secret/data/app/dadata"
    
    api_key: Optional[str] = Field(default=None, description="API ключ DaData")
    api_url: str = Field(
        default="https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party",
        description="URL DaData API"
    )
    
    # Таймауты
    timeout: float = Field(default=30.0, description="Таймаут запроса (сек)")
    
    # Кеш
    cache_ttl: int = Field(default=7200, description="TTL кеша (сек)")
    
    # Rate limiting
    rate_limit_per_second: int = Field(default=10, description="Лимит запросов в секунду")
    
    class Config:
        env_prefix = "DADATA_"


class CasebookAPISettings(BaseSettingsWithLoader):
    """Настройки Casebook API."""
    
    yaml_group = "casebook"
    vault_path = "secret/data/app/casebook"
    
    api_key: Optional[str] = Field(default=None, description="API ключ Casebook")
    arbitr_url: str = Field(
        default="https://api3.casebook.ru/arbitrage/cases",
        description="URL Casebook Arbitrage API"
    )
    
    # Таймауты
    timeout: float = Field(default=30.0, description="Таймаут запроса (сек)")
    
    # Кеш
    cache_ttl: int = Field(default=9600, description="TTL кеша (сек)")
    
    # Пагинация
    page_size: int = Field(default=100, description="Размер страницы")
    
    class Config:
        env_prefix = "CASEBOOK_"


class InfoSphereAPISettings(BaseSettingsWithLoader):
    """Настройки InfoSphere API."""
    
    yaml_group = "infosphere"
    vault_path = "secret/data/app/infosphere"
    
    login: Optional[str] = Field(default=None, description="Логин InfoSphere")
    password: Optional[str] = Field(default=None, description="Пароль InfoSphere")
    api_url: str = Field(
        default="https://i-sphere.ru/2.00/",
        description="URL InfoSphere API"
    )
    
    # Таймауты
    timeout: float = Field(default=45.0, description="Таймаут запроса (сек)")
    
    # Кеш
    cache_ttl: int = Field(default=3600, description="TTL кеша (сек)")
    
    # Источники для проверки
    sources: str = Field(
        default="fssp,bankrot,cbr,egrul,fns,fsin,fmsdb,fms,gosuslugi,mvd,pfr,terrorist",
        description="Список источников для проверки"
    )
    
    class Config:
        env_prefix = "INFOSPHERE_"


class PerplexityAPISettings(BaseSettingsWithLoader):
    """Настройки Perplexity AI API."""
    
    yaml_group = "perplexity"
    vault_path = "secret/data/app/perplexity"
    
    api_key: Optional[str] = Field(default=None, description="API ключ Perplexity")
    api_url: str = Field(
        default="https://api.perplexity.ai",
        description="URL Perplexity API"
    )
    model: str = Field(default="sonar-pro", description="Модель Perplexity")
    
    # Параметры запросов
    temperature: float = Field(default=0.2, description="Temperature для генерации")
    max_tokens: Optional[int] = Field(default=None, description="Максимум токенов в ответе")
    search_recency_filter: str = Field(default="month", description="Фильтр давности поиска")
    
    # Таймауты
    timeout: float = Field(default=60.0, description="Таймаут запроса (сек)")
    
    # Кеш
    cache_ttl: int = Field(default=300, description="TTL кеша (сек)")
    cache_enabled: bool = Field(default=True, description="Включить кеш")
    
    class Config:
        env_prefix = "PERPLEXITY_"


class TavilyAPISettings(BaseSettingsWithLoader):
    """Настройки Tavily Search API."""
    
    yaml_group = "tavily"
    vault_path = "secret/data/app/tavily"
    
    api_key: Optional[str] = Field(default=None, description="API ключ Tavily", alias="TAVILY_TOKEN")
    
    # Параметры поиска
    search_depth: str = Field(default="advanced", description="Глубина поиска (basic/advanced)")
    max_results: int = Field(default=10, description="Максимум результатов")
    include_answer: bool = Field(default=True, description="Включить сгенерированный ответ")
    include_raw_content: bool = Field(default=False, description="Включить сырой контент")
    
    # Таймауты
    timeout: float = Field(default=60.0, description="Таймаут запроса (сек)")
    
    # Кеш
    cache_ttl: int = Field(default=300, description="TTL кеша (сек)")
    cache_enabled: bool = Field(default=True, description="Включить кеш")
    
    class Config:
        env_prefix = "TAVILY_"


class OpenRouterAPISettings(BaseSettingsWithLoader):
    """Настройки OpenRouter API (LLM провайдер)."""
    
    yaml_group = "openrouter"
    vault_path = "secret/data/app/openrouter"
    
    api_key: Optional[str] = Field(default=None, description="API ключ OpenRouter")
    api_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="URL OpenRouter API"
    )
    model: str = Field(
        default="anthropic/claude-3.5-sonnet",
        description="Модель LLM"
    )
    
    # Параметры генерации
    temperature: float = Field(default=0.1, description="Temperature для генерации")
    max_tokens: int = Field(default=1000, description="Максимум токенов")
    top_p: float = Field(default=1.0, description="Top-p sampling")
    
    # Таймауты
    timeout: float = Field(default=60.0, description="Таймаут запроса (сек)")
    
    class Config:
        env_prefix = "OPENROUTER_"


# Алиас для обратной совместимости
SKBAPISettings = InfoSphereAPISettings


# Singleton экземпляры
http_base_settings = HttpBaseSettings.get_instance()
dadata_api_settings = DadataAPISettings.get_instance()
casebook_api_settings = CasebookAPISettings.get_instance()
infosphere_api_settings = InfoSphereAPISettings.get_instance()
skb_api_settings = infosphere_api_settings  # Алиас
perplexity_api_settings = PerplexityAPISettings.get_instance()
tavily_api_settings = TavilyAPISettings.get_instance()
openrouter_api_settings = OpenRouterAPISettings.get_instance()


__all__ = [
    "HttpBaseSettings",
    "DadataAPISettings",
    "CasebookAPISettings",
    "InfoSphereAPISettings",
    "SKBAPISettings",
    "PerplexityAPISettings",
    "TavilyAPISettings",
    "OpenRouterAPISettings",
    "http_base_settings",
    "dadata_api_settings",
    "casebook_api_settings",
    "infosphere_api_settings",
    "skb_api_settings",
    "perplexity_api_settings",
    "tavily_api_settings",
    "openrouter_api_settings",
]

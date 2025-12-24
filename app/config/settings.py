"""
Корневая конфигурация приложения.

Важно:
- Pydantic BaseModel по умолчанию копирует значения полей-других моделей,
  поэтому "Settings(BaseSettings)" с полями типа BaseSettingsWithLoader
  не подходит для hot-reload (получаются копии).

Решение:
- Settings — это лёгкий facade с @property, который всегда возвращает
  singleton-экземпляры через get_instance(). Тогда обновления, сделанные
  через watchdog/reload, автоматически видны всем потребителям.
"""

from app.config.base import (
    AppBaseSettings,
    SchedulerSettings,
    app_base_settings,
    scheduler_settings,
)
from app.config.database import (
    DatabaseConnectionSettings,
    MongoConnectionSettings,
    TarantoolConnectionSettings,
    db_connection_settings,
    mongo_connection_settings,
    tarantool_settings,
)
from app.config.external_api import (
    CasebookAPISettings,
    DadataAPISettings,
    GigaChatAPISettings,
    HttpBaseSettings,
    HuggingFaceAPISettings,
    InfoSphereAPISettings,
    OpenRouterAPISettings,
    PerplexityAPISettings,
    SKBAPISettings,
    TavilyAPISettings,
    YandexGPTAPISettings,
    casebook_api_settings,
    dadata_api_settings,
    http_base_settings,
    infosphere_api_settings,
    openrouter_api_settings,
    perplexity_api_settings,
    skb_api_settings,
    tavily_api_settings,
    yandexgpt_api_settings,
)
from app.config.security import SecureSettings, secure_settings
from app.config.services import (
    CelerySettings,
    FileStorageSettings,
    GRPCSettings,
    LogStorageSettings,
    MailSettings,
    QueueSettings,
    RedisSettings,
    TasksSettings,
    celery_settings,
    fs_settings,
    grpc_settings,
    log_settings,
    mail_settings,
    queue_settings,
    redis_settings,
    tasks_settings,
)


class Settings:
    """Facade around singleton settings groups (hot-reload friendly)."""

    # Base
    @property
    def app(self) -> AppBaseSettings:
        return AppBaseSettings.get_instance()

    @property
    def scheduler(self) -> SchedulerSettings:
        return SchedulerSettings.get_instance()

    @property
    def secure(self) -> SecureSettings:
        return SecureSettings.get_instance()

    # HTTP base
    @property
    def http_base(self) -> HttpBaseSettings:
        return HttpBaseSettings.get_instance()

    # Databases
    @property
    def tarantool(self) -> TarantoolConnectionSettings:
        return TarantoolConnectionSettings.get_instance()

    @property
    def database(self) -> DatabaseConnectionSettings:
        # alias
        return DatabaseConnectionSettings.get_instance()

    @property
    def mongo(self) -> MongoConnectionSettings:
        return MongoConnectionSettings.get_instance()

    @property
    def redis(self) -> RedisSettings:
        return RedisSettings.get_instance()

    # External APIs
    @property
    def dadata(self) -> DadataAPISettings:
        return DadataAPISettings.get_instance()

    @property
    def casebook(self) -> CasebookAPISettings:
        return CasebookAPISettings.get_instance()

    @property
    def infosphere(self) -> InfoSphereAPISettings:
        return InfoSphereAPISettings.get_instance()

    @property
    def skb_api(self) -> SKBAPISettings:
        return SKBAPISettings.get_instance()

    @property
    def perplexity(self) -> PerplexityAPISettings:
        return PerplexityAPISettings.get_instance()

    @property
    def tavily(self) -> TavilyAPISettings:
        return TavilyAPISettings.get_instance()

    @property
    def openrouter(self) -> OpenRouterAPISettings:
        return OpenRouterAPISettings.get_instance()

    @property
    def huggingface(self) -> HuggingFaceAPISettings:
        return HuggingFaceAPISettings.get_instance()

    @property
    def gigachat(self) -> GigaChatAPISettings:
        return GigaChatAPISettings.get_instance()

    @property
    def yandexgpt(self) -> YandexGPTAPISettings:
        return YandexGPTAPISettings.get_instance()

    # Internal services
    @property
    def queue(self) -> QueueSettings:
        return QueueSettings.get_instance()

    @property
    def celery(self) -> CelerySettings:
        return CelerySettings.get_instance()

    @property
    def mail(self) -> MailSettings:
        return MailSettings.get_instance()

    @property
    def grpc(self) -> GRPCSettings:
        return GRPCSettings.get_instance()

    @property
    def tasks(self) -> TasksSettings:
        return TasksSettings.get_instance()

    # Storage/logging
    @property
    def storage(self) -> FileStorageSettings:
        return FileStorageSettings.get_instance()

    @property
    def logging(self) -> LogStorageSettings:
        return LogStorageSettings.get_instance()


# Единый экземпляр настроек приложения (facade)
settings = Settings()


# Backward compatibility - экспортируем отдельные настройки
__all__ = [
    "Settings",
    "settings",
    # Base
    "AppBaseSettings",
    "SchedulerSettings",
    "app_base_settings",
    "scheduler_settings",
    # Security
    "SecureSettings",
    "secure_settings",
    # Database
    "TarantoolConnectionSettings",
    "DatabaseConnectionSettings",
    "MongoConnectionSettings",
    "tarantool_settings",
    "db_connection_settings",
    "mongo_connection_settings",
    # External API
    "HttpBaseSettings",
    "DadataAPISettings",
    "CasebookAPISettings",
    "InfoSphereAPISettings",
    "SKBAPISettings",
    "PerplexityAPISettings",
    "TavilyAPISettings",
    "OpenRouterAPISettings",
    "YandexGPTAPISettings",
    "http_base_settings",
    "dadata_api_settings",
    "casebook_api_settings",
    "infosphere_api_settings",
    "skb_api_settings",
    "perplexity_api_settings",
    "tavily_api_settings",
    "openrouter_api_settings",
    "yandexgpt_api_settings",
    # Services
    "RedisSettings",
    "QueueSettings",
    "CelerySettings",
    "MailSettings",
    "TasksSettings",
    "FileStorageSettings",
    "LogStorageSettings",
    "GRPCSettings",
    "redis_settings",
    "queue_settings",
    "celery_settings",
    "mail_settings",
    "tasks_settings",
    "fs_settings",
    "log_settings",
    "grpc_settings",
]

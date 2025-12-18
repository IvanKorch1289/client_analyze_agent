"""
Корневая конфигурация приложения.

Объединяет все компоненты конфигурации в единую структуру Settings.
Использует каскадную загрузку: Vault > Env > YAML.
"""

from pydantic_settings import BaseSettings

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
    HttpBaseSettings,
    InfoSphereAPISettings,
    OpenRouterAPISettings,
    PerplexityAPISettings,
    SKBAPISettings,
    TavilyAPISettings,
    casebook_api_settings,
    dadata_api_settings,
    http_base_settings,
    infosphere_api_settings,
    openrouter_api_settings,
    perplexity_api_settings,
    skb_api_settings,
    tavily_api_settings,
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


class Settings(BaseSettings):
    """
    Корневая конфигурация приложения.

    Объединяет все компоненты конфигурации:
    - Общие настройки приложения (app, scheduler)
    - Безопасность (secure)
    - Базы данных и хранилища (tarantool, mongo, redis)
    - Внешние API (dadata, casebook, infosphere, perplexity, tavily, openrouter)
    - Внутренние сервисы (queue, celery, mail, grpc)
    - Хранилища (storage, logging)
    - Фоновые задачи (tasks)
    
    Пример использования:
        from app.config.settings import settings
        
        print(settings.app.app_name)
        print(settings.tarantool.host)
        print(settings.perplexity.api_key)
    """

    # Общие настройки
    app: AppBaseSettings = app_base_settings
    scheduler: SchedulerSettings = scheduler_settings
    secure: SecureSettings = secure_settings
    
    # HTTP базовые настройки
    http_base: HttpBaseSettings = http_base_settings

    # Базы данных и хранилища
    tarantool: TarantoolConnectionSettings = tarantool_settings
    database: DatabaseConnectionSettings = db_connection_settings  # Алиас
    mongo: MongoConnectionSettings = mongo_connection_settings
    redis: RedisSettings = redis_settings
    
    # Внешние API
    dadata: DadataAPISettings = dadata_api_settings
    casebook: CasebookAPISettings = casebook_api_settings
    infosphere: InfoSphereAPISettings = infosphere_api_settings
    skb_api: SKBAPISettings = skb_api_settings  # Алиас
    perplexity: PerplexityAPISettings = perplexity_api_settings
    tavily: TavilyAPISettings = tavily_api_settings
    openrouter: OpenRouterAPISettings = openrouter_api_settings

    # Внутренние сервисы
    queue: QueueSettings = queue_settings
    celery: CelerySettings = celery_settings
    mail: MailSettings = mail_settings
    grpc: GRPCSettings = grpc_settings
    tasks: TasksSettings = tasks_settings
    
    # Хранилища
    storage: FileStorageSettings = fs_settings
    logging: LogStorageSettings = log_settings


# Единый экземпляр настроек приложения
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
    "http_base_settings",
    "dadata_api_settings",
    "casebook_api_settings",
    "infosphere_api_settings",
    "skb_api_settings",
    "perplexity_api_settings",
    "tavily_api_settings",
    "openrouter_api_settings",
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

"""
Настройки внутренних сервисов.

Содержит конфигурацию для:
- Redis (кеш, сессии)
- RabbitMQ / Celery (очереди задач)
- Email / SMTP (уведомления)
- GRPC (межсервисное взаимодействие)
- Хранилища файлов
"""

from typing import Optional

from pydantic import ConfigDict, Field

from app.config.config_loader import BaseSettingsWithLoader


class RedisSettings(BaseSettingsWithLoader):
    """Настройки Redis."""
    
    yaml_group = "redis"
    vault_path = "secret/data/app/redis"
    
    # Подключение
    host: str = Field(default="localhost", description="Хост Redis")
    port: int = Field(default=6379, description="Порт Redis")
    db: int = Field(default=0, description="Номер БД Redis")
    password: Optional[str] = Field(default=None, description="Пароль Redis")
    
    # Пул соединений
    max_connections: int = Field(default=10, description="Максимум соединений в пуле")
    socket_timeout: float = Field(default=5.0, description="Таймаут сокета (сек)")
    socket_connect_timeout: float = Field(default=5.0, description="Таймаут подключения (сек)")
    
    # TTL по умолчанию
    default_ttl: int = Field(default=3600, description="TTL по умолчанию (сек)")
    
    # Кодировка
    encoding: str = Field(default="utf-8", description="Кодировка")
    decode_responses: bool = Field(default=True, description="Декодировать ответы")
    
    @property
    def url(self) -> str:
        """Redis URL для подключения."""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"
    
    model_config = ConfigDict(env_prefix="REDIS_")


class QueueSettings(BaseSettingsWithLoader):
    """Настройки RabbitMQ очереди."""
    
    yaml_group = "queue"
    vault_path = "secret/data/app/rabbitmq"
    
    # Подключение
    host: str = Field(default="localhost", description="Хост RabbitMQ")
    port: int = Field(default=5672, description="Порт AMQP")
    username: str = Field(default="admin", description="Пользователь")
    password: str = Field(default="admin123", description="Пароль")
    vhost: str = Field(default="/", description="Virtual host")
    
    # Management UI
    management_port: int = Field(default=15672, description="Порт Management UI")
    
    # Очереди
    analysis_queue: str = Field(default="analysis.client", description="Очередь анализа клиентов")
    reports_queue: str = Field(default="reports.generate", description="Очередь генерации отчётов")
    notifications_queue: str = Field(default="notifications.email", description="Очередь уведомлений")
    cache_queue: str = Field(default="cache.invalidate", description="Очередь инвалидации кеша")
    
    # Настройки обработки
    prefetch_count: int = Field(default=10, description="Количество предзагрузки сообщений")
    max_retries: int = Field(default=3, description="Максимум повторных попыток")
    retry_delay: int = Field(default=5, description="Задержка между попытками (сек)")
    
    # Dead Letter Queue
    dlq_enabled: bool = Field(default=True, description="Включить DLQ")
    dlq_ttl: int = Field(default=86400, description="TTL сообщений в DLQ (сек)")

    # Режим выполнения задач
    enabled: bool = Field(
        default=False,
        description="Включить выполнение задач через RabbitMQ/FastStream (иначе in-process)",
    )
    
    @property
    def amqp_url(self) -> str:
        """AMQP URL для подключения."""
        return f"amqp://{self.username}:{self.password}@{self.host}:{self.port}{self.vhost}"
    
    model_config = ConfigDict(env_prefix="RABBITMQ_")


class CelerySettings(BaseSettingsWithLoader):
    """Настройки Celery (если используется вместо FastStream)."""
    
    yaml_group = "celery"
    vault_path = "secret/data/app/celery"
    
    # Broker
    broker_url: Optional[str] = Field(default=None, description="URL брокера Celery")
    result_backend: Optional[str] = Field(default=None, description="URL backend результатов")
    
    # Настройки воркеров
    worker_concurrency: int = Field(default=4, description="Количество параллельных воркеров")
    worker_prefetch_multiplier: int = Field(default=4, description="Множитель prefetch")
    worker_max_tasks_per_child: int = Field(default=1000, description="Максимум задач на воркер")
    
    # Таймауты
    task_soft_time_limit: int = Field(default=300, description="Мягкий лимит времени задачи (сек)")
    task_time_limit: int = Field(default=600, description="Жесткий лимит времени задачи (сек)")
    
    # Retry
    task_acks_late: bool = Field(default=True, description="Подтверждать задачи после выполнения")
    task_reject_on_worker_lost: bool = Field(default=True, description="Отклонять при потере воркера")
    
    # Результаты
    result_expires: int = Field(default=3600, description="Время хранения результатов (сек)")
    
    model_config = ConfigDict(env_prefix="CELERY_")


class MailSettings(BaseSettingsWithLoader):
    """Настройки SMTP для email уведомлений."""
    
    yaml_group = "mail"
    vault_path = "secret/data/app/smtp"
    
    # SMTP сервер
    smtp_host: str = Field(default="", description="Хост SMTP сервера")
    smtp_port: int = Field(default=587, description="Порт SMTP")
    smtp_user: str = Field(default="", description="Пользователь SMTP")
    smtp_password: str = Field(default="", description="Пароль SMTP")
    smtp_from: str = Field(default="", description="Email отправителя")
    
    # TLS/SSL
    smtp_use_tls: bool = Field(default=True, description="Использовать TLS")
    smtp_use_ssl: bool = Field(default=False, description="Использовать SSL")
    
    # Таймауты
    smtp_timeout: int = Field(default=10, description="Таймаут SMTP (сек)")
    
    # Шаблоны
    templates_dir: str = Field(default="templates/email", description="Директория шаблонов")
    
    # Уведомления
    enable_notifications: bool = Field(default=False, description="Включить email уведомления")
    admin_emails: list[str] = Field(default=[], description="Email'ы администраторов")
    
    model_config = ConfigDict(env_prefix="SMTP_")


class TasksSettings(BaseSettingsWithLoader):
    """Настройки фоновых задач."""
    
    yaml_group = "tasks"
    vault_path = "secret/data/app/tasks"
    
    # Включение задач
    enabled: bool = Field(default=True, description="Включить фоновые задачи")
    
    # Типы задач
    enable_cleanup: bool = Field(default=True, description="Включить очистку старых данных")
    enable_healthchecks: bool = Field(default=True, description="Включить healthcheck'и")
    enable_reports_generation: bool = Field(default=True, description="Включить генерацию отчётов")
    
    # Интервалы (секунды)
    cleanup_interval: int = Field(default=3600, description="Интервал очистки")
    healthcheck_interval: int = Field(default=300, description="Интервал healthcheck")
    
    model_config = ConfigDict(env_prefix="TASKS_")


class FileStorageSettings(BaseSettingsWithLoader):
    """Настройки хранилища файлов."""
    
    yaml_group = "storage"
    vault_path = "secret/data/app/storage"
    
    # Локальное хранилище
    local_storage_path: str = Field(default="./storage", description="Путь к локальному хранилищу")
    reports_path: str = Field(default="./reports", description="Путь к отчётам")
    logs_path: str = Field(default="./logs", description="Путь к логам")
    temp_path: str = Field(default="./temp", description="Путь к временным файлам")
    
    # S3 (опционально)
    s3_enabled: bool = Field(default=False, description="Использовать S3")
    s3_bucket: Optional[str] = Field(default=None, description="S3 bucket")
    s3_access_key: Optional[str] = Field(default=None, description="S3 access key")
    s3_secret_key: Optional[str] = Field(default=None, description="S3 secret key")
    s3_region: str = Field(default="us-east-1", description="S3 region")
    s3_endpoint: Optional[str] = Field(default=None, description="Custom S3 endpoint")
    
    # Лимиты
    max_file_size_mb: int = Field(default=10, description="Максимальный размер файла (MB)")
    max_upload_size_mb: int = Field(default=100, description="Максимальный размер загрузки (MB)")
    
    model_config = ConfigDict(env_prefix="STORAGE_")


class LogStorageSettings(BaseSettingsWithLoader):
    """Настройки хранения логов."""
    
    yaml_group = "logging"
    vault_path = "secret/data/app/logging"
    
    # Общие настройки
    level: str = Field(default="INFO", description="Уровень логирования")
    format: str = Field(default="json", description="Формат логов (json/text)")
    
    # Файловое логирование
    file_enabled: bool = Field(default=True, description="Логирование в файл")
    file_path: str = Field(default="./logs", description="Путь к файлам логов")
    file_rotation: str = Field(default="daily", description="Ротация логов (daily/size)")
    file_max_size_mb: int = Field(default=100, description="Максимальный размер файла (MB)")
    file_backup_count: int = Field(default=7, description="Количество бекапов")
    
    # Структурированное логирование
    structured_enabled: bool = Field(default=True, description="Структурированные логи")
    
    # External logging (опционально)
    sentry_enabled: bool = Field(default=False, description="Отправка в Sentry")
    sentry_dsn: Optional[str] = Field(default=None, description="Sentry DSN")
    
    elasticsearch_enabled: bool = Field(default=False, description="Отправка в Elasticsearch")
    elasticsearch_url: Optional[str] = Field(default=None, description="Elasticsearch URL")
    
    model_config = ConfigDict(env_prefix="LOG_")


class GRPCSettings(BaseSettingsWithLoader):
    """Настройки gRPC сервера (опционально)."""
    
    yaml_group = "grpc"
    vault_path = "secret/data/app/grpc"
    
    # Сервер
    enabled: bool = Field(default=False, description="Включить gRPC сервер")
    host: str = Field(default="0.0.0.0", description="Хост gRPC")
    port: int = Field(default=50051, description="Порт gRPC")
    
    # Настройки
    max_workers: int = Field(default=10, description="Максимум воркеров")
    max_message_length: int = Field(default=4 * 1024 * 1024, description="Максимальный размер сообщения")
    
    # TLS
    tls_enabled: bool = Field(default=False, description="Включить TLS")
    tls_cert_path: Optional[str] = Field(default=None, description="Путь к сертификату")
    tls_key_path: Optional[str] = Field(default=None, description="Путь к ключу")
    
    model_config = ConfigDict(env_prefix="GRPC_")


# Singleton экземпляры
redis_settings = RedisSettings.get_instance()
queue_settings = QueueSettings.get_instance()
celery_settings = CelerySettings.get_instance()
mail_settings = MailSettings.get_instance()
tasks_settings = TasksSettings.get_instance()
fs_settings = FileStorageSettings.get_instance()
log_settings = LogStorageSettings.get_instance()
grpc_settings = GRPCSettings.get_instance()


__all__ = [
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

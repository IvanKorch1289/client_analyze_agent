"""
Базовые настройки приложения.

Содержит общие настройки, которые не относятся к конкретным сервисам.
"""

from typing import Optional

from pydantic import ConfigDict, Field

from app.config.config_loader import BaseSettingsWithLoader


class AppBaseSettings(BaseSettingsWithLoader):
    """Основные настройки приложения."""
    
    yaml_group = "app"
    vault_path = "secret/data/app/base"
    
    # Идентификация приложения
    app_name: str = Field(default="counterparty-analyzer", description="Название приложения")
    app_version: str = Field(default="0.1.0", description="Версия приложения")
    environment: str = Field(default="dev", description="Окружение (dev/staging/prod)")
    
    # Порты
    backend_port: int = Field(default=8000, description="Порт FastAPI backend")
    streamlit_port: int = Field(default=5000, description="Порт Streamlit frontend")
    mcp_server_port: int = Field(default=8001, description="Порт MCP сервера")
    
    # Режимы работы
    debug: bool = Field(default=True, description="Режим отладки")
    reload: bool = Field(default=True, description="Auto-reload при изменении кода")
    
    # Логирование
    log_level: str = Field(default="INFO", description="Уровень логирования")
    log_format: str = Field(default="json", description="Формат логов (json/text)")
    
    # CORS
    cors_origins: list[str] = Field(
        default=["http://localhost:5000", "http://localhost:8000"],
        description="Разрешенные CORS origins"
    )
    
    # Производительность
    workers: int = Field(default=1, description="Количество worker процессов")
    max_requests: int = Field(default=1000, description="Максимум запросов до перезапуска worker")
    
    model_config = ConfigDict(env_prefix="APP_")


class SchedulerSettings(BaseSettingsWithLoader):
    """Настройки планировщика задач."""
    
    yaml_group = "scheduler"
    vault_path = "secret/data/app/scheduler"
    
    # Включение планировщика
    enabled: bool = Field(default=False, description="Включить фоновый планировщик")
    
    # Интервалы выполнения задач (в секундах)
    cleanup_interval: int = Field(default=3600, description="Интервал очистки старых данных")
    healthcheck_interval: int = Field(default=300, description="Интервал проверки здоровья сервисов")
    cache_cleanup_interval: int = Field(default=1800, description="Интервал очистки кеша")
    
    # Время жизни данных
    old_reports_ttl_days: int = Field(default=30, description="TTL для старых отчётов (дни)")
    old_logs_ttl_days: int = Field(default=7, description="TTL для старых логов (дни)")
    
    model_config = ConfigDict(env_prefix="SCHEDULER_")


# Singleton экземпляры
app_base_settings = AppBaseSettings.get_instance()
scheduler_settings = SchedulerSettings.get_instance()


__all__ = [
    "AppBaseSettings",
    "SchedulerSettings",
    "app_base_settings",
    "scheduler_settings",
]

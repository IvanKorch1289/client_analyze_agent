"""
Настройки подключения к базам данных и хранилищам.

Содержит конфигурацию для:
- Tarantool (основное хранилище кеша и отчётов)
- MongoDB (опционально, для будущего использования)
"""

from typing import Optional

from pydantic import Field

from app.config.config_loader import BaseSettingsWithLoader


class TarantoolConnectionSettings(BaseSettingsWithLoader):
    """Настройки подключения к Tarantool."""
    
    yaml_group = "tarantool"
    vault_path = "secret/data/app/tarantool"
    
    # Подключение
    host: str = Field(default="localhost", description="Хост Tarantool")
    port: int = Field(default=3302, description="Порт Tarantool")
    user: str = Field(default="admin", description="Пользователь")
    password: str = Field(default="password", description="Пароль")
    
    # Настройки соединения
    connect_timeout: float = Field(default=5.0, description="Таймаут подключения (сек)")
    reconnect_max_attempts: int = Field(default=3, description="Максимум попыток переподключения")
    reconnect_delay: float = Field(default=1.0, description="Задержка между попытками (сек)")
    
    # Пулы соединений
    pool_size: int = Field(default=10, description="Размер пула соединений")
    
    # Fallback режим
    use_memory_fallback: bool = Field(default=True, description="Использовать in-memory при недоступности")
    
    # Spaces
    cache_space: str = Field(default="cache", description="Space для кеша")
    reports_space: str = Field(default="reports", description="Space для отчётов")
    threads_space: str = Field(default="threads", description="Space для тредов")
    persistent_space: str = Field(default="persistent", description="Space для постоянных данных")
    
    class Config:
        env_prefix = "TARANTOOL_"


class MongoConnectionSettings(BaseSettingsWithLoader):
    """Настройки подключения к MongoDB (опционально)."""
    
    yaml_group = "mongo"
    vault_path = "secret/data/app/mongo"
    
    # Подключение
    host: str = Field(default="localhost", description="Хост MongoDB")
    port: int = Field(default=27017, description="Порт MongoDB")
    database: str = Field(default="counterparty_analyzer", description="Название БД")
    username: Optional[str] = Field(default=None, description="Пользователь")
    password: Optional[str] = Field(default=None, description="Пароль")
    
    # Настройки соединения
    min_pool_size: int = Field(default=1, description="Минимальный размер пула")
    max_pool_size: int = Field(default=10, description="Максимальный размер пула")
    connect_timeout_ms: int = Field(default=5000, description="Таймаут подключения (мс)")
    server_selection_timeout_ms: int = Field(default=5000, description="Таймаут выбора сервера (мс)")
    
    # Опции
    auth_source: str = Field(default="admin", description="База для аутентификации")
    replica_set: Optional[str] = Field(default=None, description="Имя replica set")
    
    @property
    def connection_string(self) -> str:
        """Генерация MongoDB connection string."""
        if self.username and self.password:
            auth = f"{self.username}:{self.password}@"
        else:
            auth = ""
        
        options = f"?authSource={self.auth_source}"
        if self.replica_set:
            options += f"&replicaSet={self.replica_set}"
        
        return f"mongodb://{auth}{self.host}:{self.port}/{self.database}{options}"
    
    class Config:
        env_prefix = "MONGO_"


# Алиас для обратной совместимости
DatabaseConnectionSettings = TarantoolConnectionSettings


# Singleton экземпляры
tarantool_settings = TarantoolConnectionSettings.get_instance()
db_connection_settings = tarantool_settings  # Алиас
mongo_connection_settings = MongoConnectionSettings.get_instance()


__all__ = [
    "TarantoolConnectionSettings",
    "MongoConnectionSettings",
    "DatabaseConnectionSettings",
    "tarantool_settings",
    "db_connection_settings",
    "mongo_connection_settings",
]

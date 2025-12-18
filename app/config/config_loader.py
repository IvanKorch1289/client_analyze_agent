"""
Централизованный загрузчик конфигурации.

Поддерживает загрузку из:
1. HashiCorp Vault (приоритет 1)
2. Environment variables (приоритет 2)
3. YAML файлы (приоритет 3)

Пример использования:
    from app.config.database import DatabaseConnectionSettings
    
    db_settings = DatabaseConnectionSettings()
    print(db_settings.host)  # Загружено из Vault/Env/YAML
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional, Type, TypeVar

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Типизация для Generic Settings
T = TypeVar("T", bound=BaseSettings)


class ConfigLoader:
    """
    Централизованный загрузчик конфигурации с каскадным приоритетом.
    
    Приоритет источников:
    1. HashiCorp Vault (если доступен)
    2. Environment variables
    3. YAML файлы
    """
    
    # Кеш для конфигураций
    _cache: Dict[str, Any] = {}
    
    # Путь к YAML конфигурациям
    YAML_CONFIG_DIR = Path("config")
    
    # Текущее окружение (dev, staging, prod)
    ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")
    
    @classmethod
    def get_vault_client(cls):
        """
        Получить клиент HashiCorp Vault.
        
        Returns:
            hvac.Client или None если Vault не доступен
        """
        try:
            import hvac
            
            vault_addr = os.getenv("VAULT_ADDR")
            vault_token = os.getenv("VAULT_TOKEN")
            
            if not vault_addr or not vault_token:
                return None
            
            client = hvac.Client(url=vault_addr, token=vault_token)
            
            # Проверка подключения
            if not client.is_authenticated():
                return None
            
            return client
        except ImportError:
            # hvac не установлен
            return None
        except Exception:
            # Ошибка подключения к Vault
            return None
    
    @classmethod
    def load_from_vault(cls, path: str, key: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Загрузка конфигурации из Vault.
        
        Args:
            path: Путь в Vault (например: "secret/data/app/database")
            key: Конкретный ключ (опционально, вернет весь секрет если None)
            
        Returns:
            Dict с конфигурацией или None если не найдено
        """
        cache_key = f"vault:{path}:{key}"
        if cache_key in cls._cache:
            return cls._cache[cache_key]
        
        client = cls.get_vault_client()
        if not client:
            return None
        
        try:
            # Читаем секрет из Vault
            response = client.secrets.kv.v2.read_secret_version(path=path)
            data = response["data"]["data"]
            
            result = data.get(key) if key else data
            cls._cache[cache_key] = result
            return result
        except Exception:
            return None
    
    @classmethod
    def load_from_yaml(cls, filename: str, group: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Загрузка конфигурации из YAML файла.
        
        Args:
            filename: Имя YAML файла (например: "database.yaml")
            group: Группа конфигурации (опционально)
            
        Returns:
            Dict с конфигурацией или None если не найдено
        """
        cache_key = f"yaml:{filename}:{group}"
        if cache_key in cls._cache:
            return cls._cache[cache_key]
        
        # Проверяем файл для текущего окружения (например: database.dev.yaml)
        env_filename = filename.replace(".yaml", f".{cls.ENVIRONMENT}.yaml")
        yaml_path = cls.YAML_CONFIG_DIR / env_filename
        
        # Если нет файла для окружения, используем базовый
        if not yaml_path.exists():
            yaml_path = cls.YAML_CONFIG_DIR / filename
        
        if not yaml_path.exists():
            return None
        
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            
            result = data.get(group) if group else data
            cls._cache[cache_key] = result
            return result
        except Exception:
            return None
    
    @classmethod
    def clear_cache(cls):
        """Очистить кеш конфигураций."""
        cls._cache.clear()


class BaseSettingsWithLoader(BaseSettings):
    """
    Базовый класс для настроек с поддержкой каскадной загрузки.
    
    Пример использования:
        class DatabaseSettings(BaseSettingsWithLoader):
            yaml_group = "database"
            vault_path = "secret/data/app/database"
            
            host: str = "localhost"
            port: int = 5432
    """
    
    # Путь в Vault (переопределяется в наследниках)
    vault_path: Optional[str] = None
    
    # Группа в YAML файле (переопределяется в наследниках)
    yaml_group: Optional[str] = None
    
    # Имя YAML файла (по умолчанию: имя класса в lowercase + .yaml)
    yaml_file: Optional[str] = None
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )
    
    def __init__(self, **kwargs):
        # 1. Загружаем из Vault (высший приоритет)
        vault_data = {}
        if self.vault_path:
            vault_result = ConfigLoader.load_from_vault(self.vault_path)
            if vault_result:
                vault_data = vault_result
        
        # 2. Загружаем из YAML
        yaml_data = {}
        if self.yaml_file or self.yaml_group:
            yaml_filename = self.yaml_file or f"{self.__class__.__name__.lower()}.yaml"
            yaml_result = ConfigLoader.load_from_yaml(yaml_filename, self.yaml_group)
            if yaml_result:
                yaml_data = yaml_result
        
        # 3. Environment variables загружаются автоматически через Pydantic
        # 4. Merge: Vault > Env > YAML > kwargs > defaults
        merged_data = {**yaml_data, **vault_data, **kwargs}
        
        super().__init__(**merged_data)
    
    @classmethod
    def get_instance(cls: Type[T]) -> T:
        """
        Получить singleton экземпляр настроек.
        
        Returns:
            Экземпляр настроек
        """
        cache_key = f"settings:{cls.__name__}"
        if cache_key not in ConfigLoader._cache:
            ConfigLoader._cache[cache_key] = cls()
        return ConfigLoader._cache[cache_key]

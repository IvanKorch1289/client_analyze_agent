"""
Настройки безопасности и авторизации.

Содержит:
- Токены администратора
- Секретные ключи
- Настройки JWT
- CORS политики
"""

from typing import List, Optional

from pydantic import ConfigDict, Field

from app.config.config_loader import BaseSettingsWithLoader


class SecureSettings(BaseSettingsWithLoader):
    """Настройки безопасности."""

    yaml_group = "security"
    vault_path = "secret/data/app/security"

    # Токены и ключи
    admin_token: Optional[str] = Field(default=None, description="Токен администратора")
    secret_key: Optional[str] = Field(default=None, description="Секретный ключ приложения")
    jwt_secret: Optional[str] = Field(default=None, description="Секрет для JWT токенов")

    # JWT настройки
    jwt_algorithm: str = Field(default="HS256", description="Алгоритм JWT")
    jwt_expiration_minutes: int = Field(default=60, description="Время жизни JWT (минуты)")
    jwt_refresh_expiration_days: int = Field(default=7, description="Время жизни refresh token (дни)")

    # CORS
    cors_enabled: bool = Field(default=True, description="Включить CORS")
    cors_origins: List[str] = Field(
        default=["http://localhost:5000", "http://localhost:8000"],
        description="Разрешенные CORS origins",
    )
    cors_methods: List[str] = Field(
        default=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        description="Разрешенные HTTP методы",
    )
    cors_headers: List[str] = Field(default=["*"], description="Разрешенные HTTP заголовки")
    cors_credentials: bool = Field(default=True, description="Разрешить credentials")

    # Rate Limiting (глобальные настройки)
    rate_limit_enabled: bool = Field(default=True, description="Включить rate limiting")
    rate_limit_storage: str = Field(
        default="memory://",
        description="Storage для rate limiting (memory:// или redis://)",
    )

    # IP Whitelist (опционально)
    ip_whitelist: Optional[List[str]] = Field(default=None, description="Белый список IP адресов")
    ip_blacklist: Optional[List[str]] = Field(default=None, description="Черный список IP адресов")

    # Trusted hosts (recommended for prod behind a known domain)
    trusted_hosts: Optional[List[str]] = Field(
        default=None,
        description="Allowed hosts list for TrustedHostMiddleware (e.g. ['example.com','*.example.com'])",
    )

    # Encryption
    encryption_enabled: bool = Field(default=False, description="Включить шифрование чувствительных данных")
    encryption_key: Optional[str] = Field(default=None, description="Ключ для шифрования")

    # Security Headers
    enable_security_headers: bool = Field(default=True, description="Включить security headers")
    hsts_enabled: bool = Field(default=True, description="HTTP Strict Transport Security")
    hsts_max_age: int = Field(default=31536000, description="HSTS max-age (секунды)")

    # Content Security Policy
    csp_enabled: bool = Field(default=False, description="Включить CSP")
    csp_directives: Optional[str] = Field(default=None, description="CSP directives")

    model_config = ConfigDict(env_prefix="SECURITY_")


# Singleton экземпляр
secure_settings = SecureSettings.get_instance()


__all__ = [
    "SecureSettings",
    "secure_settings",
]

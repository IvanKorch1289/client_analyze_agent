"""
Application configuration using Pydantic Settings.

All configuration is loaded from environment variables (.env file).
Never hardcode API keys or secrets in code!
"""

import os
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All sensitive data (API keys, passwords) must be in .env file.
    See .env.example for the template.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "analyze_agent"
    APP_ENV: str = Field(default="development", pattern="^(development|production|test)$")
    DEBUG: bool = False
    LOG_LEVEL: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")

    # API Keys - External Services
    DADATA_API_TOKEN: str = Field(..., min_length=10)
    DADATA_API_SECRET: str = Field(..., min_length=10)
    CASEBOOK_API_KEY: str = Field(..., min_length=10)
    INFOSFERA_API_KEY: str = Field(..., min_length=10)
    PERPLEXITY_API_KEY: str = Field(..., min_length=10)
    TAVILY_API_KEY: str = Field(..., min_length=10)
    OPENROUTER_API_KEY: str = Field(..., min_length=10)
    OPENAI_API_KEY: Optional[str] = None

    # LLM Configuration
    DEFAULT_LLM_MODEL: str = "anthropic/claude-3.5-sonnet"
    DEFAULT_TEMPERATURE: float = Field(default=0.0, ge=0.0, le=2.0)
    MAX_TOKENS: int = Field(default=4096, gt=0, le=200000)

    # Database - Tarantool
    TARANTOOL_HOST: str = "localhost"
    TARANTOOL_PORT: int = Field(default=3301, gt=0, lt=65536)
    TARANTOOL_USER: str = "admin"
    TARANTOOL_PASSWORD: str = Field(..., min_length=1)

    # RabbitMQ
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"

    # Security
    SECRET_KEY: str = Field(..., min_length=32)
    API_KEY_SALT: str = Field(..., min_length=16)

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = Field(default=60, gt=0)
    RATE_LIMIT_PER_HOUR: int = Field(default=1000, gt=0)

    # File Storage
    REPORTS_DIR: Path = Path("./reports")
    LOGS_DIR: Path = Path("./logs")

    # Streamlit UI
    STREAMLIT_SERVER_PORT: int = Field(default=8501, gt=0, lt=65536)
    STREAMLIT_SERVER_ADDRESS: str = "0.0.0.0"

    # FastAPI Backend
    FASTAPI_HOST: str = "0.0.0.0"
    FASTAPI_PORT: int = Field(default=8000, gt=0, lt=65536)

    # MCP Server
    MCP_SERVER_PORT: int = Field(default=3000, gt=0, lt=65536)

    # Monitoring & Telemetry
    ENABLE_TELEMETRY: bool = True
    TELEMETRY_ENDPOINT: str = "http://localhost:4318"

    # Email Notifications (optional)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAIL_FROM: Optional[str] = None

    @field_validator("DADATA_API_TOKEN", "DADATA_API_SECRET", "CASEBOOK_API_KEY", 
                     "INFOSFERA_API_KEY", "PERPLEXITY_API_KEY", "TAVILY_API_KEY",
                     "OPENROUTER_API_KEY", "SECRET_KEY", "API_KEY_SALT")
    @classmethod
    def validate_no_whitespace(cls, v: str) -> str:
        """Ensure API keys have no leading/trailing whitespace."""
        if v != v.strip():
            raise ValueError("API keys must not have leading/trailing whitespace")
        return v.strip()

    @field_validator("REPORTS_DIR", "LOGS_DIR")
    @classmethod
    def validate_directories(cls, v: Path) -> Path:
        """Create directories if they don't exist."""
        v.mkdir(parents=True, exist_ok=True)
        return v

    def get_api_base_url(self) -> str:
        """Get FastAPI base URL."""
        return f"http://{self.FASTAPI_HOST}:{self.FASTAPI_PORT}"

    def is_production(self) -> bool:
        """Check if running in production."""
        return self.APP_ENV == "production"

    def is_development(self) -> bool:
        """Check if running in development."""
        return self.APP_ENV == "development"


# Singleton instance
# Use this throughout the application instead of creating new instances
try:
    settings = Settings()
except Exception as e:
    print(f"❌ Failed to load configuration: {e}")
    print("📝 Make sure .env file exists and contains all required variables")
    print("📄 See .env.example for the template")
    raise


__all__ = ["settings", "Settings"]


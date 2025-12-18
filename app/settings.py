from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Tarantool
    tarantool_host: str = "localhost"
    tarantool_port: int = 3302
    tarantool_user: str = "admin"
    tarantool_password: str = "password"

    # InfoSphere
    infosphere_login: Optional[str] = None
    infosphere_password: Optional[str] = None
    infosphere_url: str = "https://i-sphere.ru/2.00/"

    # DaData
    dadata_api_key: Optional[str] = None
    dadata_url: str = (
        "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party"
    )

    # Casebook
    casebook_api_key: Optional[str] = None
    casebook_arbitr_url: str = "https://api3.casebook.ru/arbitrage/cases"

    # AI
    # Back-compat (старые имена). Оставляем, чтобы не ломать существующие .env.
    hugging_face_token: Optional[str] = None
    huging_face_model: str = "meta-llama/Meta-Llama-3-8B-Instruct"

    # Канонические имена (рекомендуемые)
    huggingface_token: Optional[str] = Field(default=None, validation_alias="HUGGINGFACE_TOKEN")
    huggingface_model: str = Field(
        default="meta-llama/Meta-Llama-3-8B-Instruct",
        validation_alias="HUGGINGFACE_MODEL",
    )

    # OpenRouter
    openrouter_api_key: Optional[str] = None
    openrouter_model: str = "anthropic/claude-3.5-sonnet"

    tavily_token: Optional[str] = None
    gigachat_token: Optional[str] = None
    gigachat_base_url: str = Field(
        default="https://gigachat.devices.sberbank.ru/api/v1",
        validation_alias="GIGACHAT_BASE_URL",
    )
    gigachat_model: str = Field(
        default="GigaChat",
        validation_alias="GIGACHAT_MODEL",
    )

    # Perplexity
    perplexity_api_key: Optional[str] = None
    perplexity_model: str = "sonar"

    temperature: float = 0.1
    max_new_tokens: int = 1000
    do_sample: bool = False

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()


def get_huggingface_token(settings: Settings) -> Optional[str]:
    return settings.huggingface_token or settings.hugging_face_token


def get_huggingface_model(settings: Settings) -> str:
    # prefer canonical name; fallback to old typo field
    return settings.huggingface_model or settings.huging_face_model

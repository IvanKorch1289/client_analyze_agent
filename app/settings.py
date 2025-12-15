from typing import Optional

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
    hugging_face_token: Optional[str] = None
    huging_face_model: str = "meta-llama/Meta-Llama-3-8B-Instruct"

    tavily_token: Optional[str] = None
    gigachat_token: Optional[str] = None
    
    # Perplexity
    perplexity_api_key: Optional[str] = None
    perplexity_model: str = "llama-3.1-sonar-small-128k-online"

    temperature: float = 0.1
    max_new_tokens: int = 1000
    do_sample: bool = False

    model_config = {
        "env_file": ".env",
        "extra": "ignore"
    }


settings = Settings()

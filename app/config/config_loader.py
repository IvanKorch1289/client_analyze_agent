from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar, Dict, Tuple, Type

from dotenv import load_dotenv
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from app.config.constants import consts

__all__ = ("BaseSettingsWithLoader",)


# Load .env once, early, for the whole app (so os.getenv also sees values).
load_dotenv(consts.ENV_FILE)


class FilteredSettingsSource(PydanticBaseSettingsSource, ABC):
    """Abstract base class for filtered settings sources."""

    def __init__(self, settings_cls: Type[BaseSettings]):
        super().__init__(settings_cls)
        self.yaml_group = getattr(settings_cls, "yaml_group", None)
        self.model_fields = set(settings_cls.model_fields.keys())

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> Tuple[Any, str, bool]:
        return (None, field_name, False)

    def __call__(self) -> Dict[str, Any]:
        try:
            raw_data = self._load_data()
            return self._filter_data(raw_data)
        except Exception:
            return {}

    def _filter_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Filter data using model fields (and optional yaml group)."""
        if self.yaml_group:
            group_data = raw_data.get(self.yaml_group, {})
            if not isinstance(group_data, dict):
                return {}
        else:
            group_data = raw_data

        if not isinstance(group_data, dict):
            return {}

        return {k: v for k, v in group_data.items() if k in self.model_fields}

    @abstractmethod
    def _load_data(self) -> Dict[str, Any]:
        """Load raw data from source."""


class YamlConfigSettingsLoader(FilteredSettingsSource):
    """YAML config loader with filtering."""

    def __init__(
        self,
        settings_cls: Type[BaseSettings],
        yaml_path: Path = consts.YAML_CONFIG,
    ):
        super().__init__(settings_cls)
        self.yaml_path = yaml_path

    def _load_data(self) -> Dict[str, Any]:
        try:
            from yaml import safe_load  # optional dependency
        except Exception:
            return {}

        try:
            with open(self.yaml_path, encoding="utf-8") as f:
                data = safe_load(f) or {}
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception:
            return {}


class VaultConfigSettingsSource(FilteredSettingsSource):
    """Vault config loader with filtering (optional)."""

    def _load_data(self) -> Dict[str, Any]:
        from os import getenv

        vault_addr = getenv("VAULT_ADDR")
        vault_token = getenv("VAULT_TOKEN")
        vault_secret_path = getenv("VAULT_SECRET_PATH")

        if not all([vault_addr, vault_token, vault_secret_path]):
            return {}

        try:
            from hvac import Client  # optional dependency
        except Exception:
            return {}

        try:
            client = Client(url=vault_addr, token=vault_token)
            if not client.is_authenticated():
                return {}

            response = client.secrets.kv.v2.read_secret_version(path=vault_secret_path)
            data = response.get("data", {}).get("data", {})
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}


class BaseSettingsWithLoader(BaseSettings):
    """
    Base class for configuration models with multi-source loading support.

    Priority order:
    1) init kwargs
    2) environment variables
    3) Vault secrets (optional)
    4) YAML config (optional)
    5) .env (pydantic dotenv source)
    6) file secrets
    """

    yaml_group: ClassVar[str | None] = None
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            VaultConfigSettingsSource(settings_cls),
            YamlConfigSettingsLoader(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )


from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class _Consts:
    ROOT_DIR: Path = Path(__file__).resolve().parents[2]
    ENV_FILE: Path = ROOT_DIR / ".env"
    YAML_CONFIG: Path = ROOT_DIR / "config.yml"


consts = _Consts()


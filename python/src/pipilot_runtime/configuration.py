"""Local Runtime configuration loaded from environment variables and .env."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"


class RuntimeConfigurationError(ValueError):
    """Raised when an explicitly requested local model configuration is incomplete."""


@dataclass(frozen=True)
class DeepSeekConfiguration:
    """Settings needed for the first OpenAI-compatible model provider."""

    api_key: str
    model: str
    base_url: str


def load_deepseek_configuration(
    environment: Mapping[str, str] | None = None,
    dotenv_path: Path | None = None,
) -> DeepSeekConfiguration | None:
    """Load an explicit DeepSeek configuration without leaking secrets into Runtime events."""

    dotenv_values = _read_dotenv(dotenv_path or Path.cwd() / ".env")
    values = {**dotenv_values, **(dict(environment) if environment is not None else os.environ)}
    model = values.get("PICODE_MODEL") or values.get("PIPILOT_MODEL")
    if model is None or not model.strip():
        return None
    if model != DEFAULT_DEEPSEEK_MODEL:
        raise RuntimeConfigurationError(f"Unsupported PICODE_MODEL: {model}")

    api_key = values.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeConfigurationError("PICODE_MODEL requires DEEPSEEK_API_KEY in .env or the environment")

    base_url = (values.get("PICODE_DEEPSEEK_BASE_URL") or values.get("PIPILOT_DEEPSEEK_BASE_URL") or DEFAULT_DEEPSEEK_BASE_URL).strip().rstrip("/")
    if not base_url:
        raise RuntimeConfigurationError("PICODE_DEEPSEEK_BASE_URL must not be empty")

    return DeepSeekConfiguration(api_key=api_key, model=model, base_url=base_url)


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition("=")
        if not separator or not key:
            raise RuntimeConfigurationError(f"Invalid .env entry in {path.name}: {line}")
        cleaned_value = value.strip()
        if len(cleaned_value) >= 2 and cleaned_value[0] == cleaned_value[-1] and cleaned_value[0] in {"'", '"'}:
            cleaned_value = cleaned_value[1:-1]
        values[key.strip()] = cleaned_value
    return values

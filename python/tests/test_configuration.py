from __future__ import annotations

from pathlib import Path

import pytest

from pipilot_runtime.configuration import RuntimeConfigurationError, load_deepseek_configuration


def test_loads_deepseek_configuration_from_dotenv(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "DEEPSEEK_API_KEY=from-dotenv\nPIPILOT_MODEL=deepseek-v4-flash\n",
        encoding="utf-8",
    )

    configuration = load_deepseek_configuration(environment={}, dotenv_path=dotenv_path)

    assert configuration is not None
    assert configuration.api_key == "from-dotenv"
    assert configuration.model == "deepseek-v4-flash"
    assert configuration.base_url == "https://api.deepseek.com"


def test_environment_overrides_dotenv(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("DEEPSEEK_API_KEY=from-dotenv\nPIPILOT_MODEL=deepseek-v4-flash\n", encoding="utf-8")

    configuration = load_deepseek_configuration(
        environment={"DEEPSEEK_API_KEY": "from-environment", "PIPILOT_MODEL": "deepseek-v4-flash"},
        dotenv_path=dotenv_path,
    )

    assert configuration is not None
    assert configuration.api_key == "from-environment"


def test_rejects_an_explicit_model_without_an_api_key(tmp_path: Path) -> None:
    with pytest.raises(RuntimeConfigurationError, match="DEEPSEEK_API_KEY"):
        load_deepseek_configuration(
            environment={"PIPILOT_MODEL": "deepseek-v4-flash"},
            dotenv_path=tmp_path / ".env",
        )

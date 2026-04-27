from __future__ import annotations

from pathlib import Path

import pytest

from parames.config import AppConfig, load_app_config


def test_default_config_parses() -> None:
    config = load_app_config(Path("config/default.yaml"))
    alert = config.alerts[0]
    assert isinstance(config, AppConfig)
    assert alert.forecast_hours == 48
    assert alert.wind_level_m == 10
    assert alert.model_agreement is not None


def test_invalid_config_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("alerts: [{}]\ndelivery_channels: {}\n", encoding="utf-8")

    with pytest.raises(ValueError):
        load_app_config(path)

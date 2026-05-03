from __future__ import annotations

from pathlib import Path

import pytest

from parames.config import AppConfig, ScoringConfig, ScoringTiersConfig, load_app_config


def test_default_config_parses() -> None:
    config = load_app_config(Path("config/default.yaml"))
    alert = config.alerts[0]
    assert isinstance(config, AppConfig)
    assert alert.forecast_hours == 48
    assert alert.wind_level_m == 10
    assert alert.model_agreement is not None


def test_default_config_includes_scoring_block() -> None:
    config = load_app_config(Path("config/default.yaml"))
    assert config.scoring.emit_threshold == 50
    assert config.scoring.tiers.strong_min == 70
    assert config.scoring.weights.wind_speed == 2.0
    assert config.scoring.weights.plugins["bise"] == 0.7


def test_scoring_defaults_when_block_omitted(tmp_path: Path) -> None:
    """A config without a `scoring:` block falls back to ScoringConfig defaults."""
    path = tmp_path / "no_scoring.yaml"
    path.write_text(
        "alerts: []\ndelivery_channels: {console: {type: console}}\n",
        encoding="utf-8",
    )
    config = load_app_config(path)
    assert config.scoring.emit_threshold == 40
    assert config.scoring.tiers.candidate_min == 40
    assert config.scoring.tiers.strong_min == 70
    assert config.scoring.tiers.excellent_min == 85


def test_scoring_tiers_must_be_strictly_ordered() -> None:
    with pytest.raises(ValueError):
        ScoringTiersConfig(candidate_min=70, strong_min=70, excellent_min=85)


def test_scoring_accepts_unknown_plugin_weight_keys() -> None:
    """Plugin weight dict should accept arbitrary type strings (forward compat)."""
    cfg = ScoringConfig.model_validate({"weights": {"plugins": {"laminar": 1.0, "bise": 0.5}}})
    assert cfg.weights.plugins["laminar"] == 1.0


def test_invalid_config_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("alerts: [{}]\ndelivery_channels: {}\n", encoding="utf-8")

    with pytest.raises(ValueError):
        load_app_config(path)

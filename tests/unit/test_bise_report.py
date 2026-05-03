from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from parames.common import LocationConfig
from parames.domain import HourForecast
from parames.plugins.bise import BisePlugin, BisePluginConfig, BisePrefetched

ZURICH = ZoneInfo("Europe/Zurich")
TS = datetime(2026, 4, 29, 12, 0, tzinfo=ZURICH)

WEST_LOC = LocationConfig(name="geneva", latitude=46.204, longitude=6.143)
EAST_LOC = LocationConfig(name="guettingen", latitude=47.604, longitude=9.287)


def _config(*, enabled: bool = True, min_hpa: float = 1.5) -> BisePluginConfig:
    return BisePluginConfig(
        enabled=enabled,
        east_minus_west_pressure_hpa_min=min_hpa,
        pressure_reference_west=WEST_LOC,
        pressure_reference_east=EAST_LOC,
    )


def _prefetched(*, west_hpa: float, east_hpa: float, model: str = "icon_d2") -> BisePrefetched:
    west_hour = HourForecast(time=TS, pressure_msl=west_hpa)
    east_hour = HourForecast(time=TS, pressure_msl=east_hpa)
    return BisePrefetched(
        west={model: {TS: west_hour}},
        east={model: {TS: east_hour}},
    )


def test_bise_report_present_on_success() -> None:
    plugin = BisePlugin(_config(min_hpa=1.5))
    pre = _prefetched(west_hpa=1013.0, east_hpa=1015.0)
    result = plugin.score_window(window_times=[TS], prefetched=pre, contributing_models=["icon_d2"])
    assert result.report is not None
    assert result.report.type == "bise"


def test_bise_report_gradient_threshold_rule_pass() -> None:
    plugin = BisePlugin(_config(min_hpa=1.5))
    pre = _prefetched(west_hpa=1013.0, east_hpa=1016.0)  # gradient=3.0 → strong, score=100
    result = plugin.score_window(window_times=[TS], prefetched=pre, contributing_models=["icon_d2"])
    assert result.sub_score == pytest.approx(100.0)
    assert result.report is not None
    rule_names = [r.name for r in result.report.rules]
    assert "gradient_threshold" in rule_names
    grad_rule = next(r for r in result.report.rules if r.name == "gradient_threshold")
    assert grad_rule.outcome == "pass"


def test_bise_report_gradient_threshold_rule_warn() -> None:
    plugin = BisePlugin(_config(min_hpa=1.5))
    pre = _prefetched(west_hpa=1013.0, east_hpa=1015.0)  # gradient=2.0 ≥ threshold
    result = plugin.score_window(window_times=[TS], prefetched=pre, contributing_models=["icon_d2"])
    assert result.sub_score == pytest.approx(75.0)
    assert result.report is not None
    grad_rule = next(r for r in result.report.rules if r.name == "gradient_threshold")
    assert grad_rule.outcome == "warn"


def test_bise_report_gradient_threshold_rule_fail() -> None:
    plugin = BisePlugin(_config(min_hpa=2.0))
    pre = _prefetched(west_hpa=1013.0, east_hpa=1014.0)  # gradient=1.0 < 2.0
    result = plugin.score_window(window_times=[TS], prefetched=pre, contributing_models=["icon_d2"])
    assert result.sub_score is None
    assert result.report is not None
    grad_rule = next(r for r in result.report.rules if r.name == "gradient_threshold")
    assert grad_rule.outcome == "fail"


def test_bise_report_data_completeness_pass() -> None:
    plugin = BisePlugin(_config())
    pre = _prefetched(west_hpa=1013.0, east_hpa=1015.5)
    result = plugin.score_window(window_times=[TS], prefetched=pre, contributing_models=["icon_d2"])
    assert result.report is not None
    comp_rule = next(r for r in result.report.rules if r.name == "data_completeness")
    assert comp_rule.outcome == "pass"


def test_bise_report_data_completeness_fail_on_missing_data() -> None:
    plugin = BisePlugin(_config())
    empty = BisePrefetched(west={}, east={})
    result = plugin.score_window(window_times=[TS], prefetched=empty, contributing_models=["icon_d2"])
    assert result.sub_score is None
    assert result.report is not None
    comp_rule = next(r for r in result.report.rules if r.name == "data_completeness")
    assert comp_rule.outcome == "fail"


def test_bise_report_metrics_populated() -> None:
    plugin = BisePlugin(_config())
    pre = _prefetched(west_hpa=1013.0, east_hpa=1015.5)
    result = plugin.score_window(window_times=[TS], prefetched=pre, contributing_models=["icon_d2"])
    assert result.report is not None
    assert "avg_gradient_hpa" in result.report.metrics
    assert "min_gradient_hpa" in result.report.metrics
    assert "max_gradient_hpa" in result.report.metrics


def test_bise_report_hourly_populated() -> None:
    plugin = BisePlugin(_config())
    pre = _prefetched(west_hpa=1013.0, east_hpa=1015.5)
    result = plugin.score_window(window_times=[TS], prefetched=pre, contributing_models=["icon_d2"])
    assert result.report is not None
    assert len(result.report.hourly) == 1
    entry = result.report.hourly[0]
    assert "time" in entry
    assert "mean_gradient_hpa" in entry
    assert "per_model_gradient_hpa" in entry


def test_bise_report_inputs_populated() -> None:
    plugin = BisePlugin(_config())
    pre = _prefetched(west_hpa=1013.0, east_hpa=1015.5)
    result = plugin.score_window(window_times=[TS], prefetched=pre, contributing_models=["icon_d2"])
    assert result.report is not None
    assert "contributing_models" in result.report.inputs
    assert "west_location" in result.report.inputs
    assert "east_location" in result.report.inputs

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from parames.common import LocationConfig
from parames.domain import HourForecast
from parames.plugins.bise import BisePlugin, BisePluginConfig, BisePrefetched

ZURICH = ZoneInfo("Europe/Zurich")

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
    ts = datetime(2026, 4, 29, 12, 0, tzinfo=ZURICH)
    west_hour = HourForecast(time=ts, pressure_msl=west_hpa)
    east_hour = HourForecast(time=ts, pressure_msl=east_hpa)
    return BisePrefetched(
        west={model: {ts: west_hour}},
        east={model: {ts: east_hour}},
    )


TS = datetime(2026, 4, 29, 12, 0, tzinfo=ZURICH)


def test_bise_below_threshold_opts_out() -> None:
    """Below-min gradient: corroboration absent → opt out (None) but still report value."""
    plugin = BisePlugin(_config(min_hpa=2.0))
    pre = _prefetched(west_hpa=1013.0, east_hpa=1014.0)  # gradient = 1.0 < 2.0
    result = plugin.score_window(
        window_times=[TS], prefetched=pre, contributing_models=["icon_d2"]
    )
    assert result.sub_score is None
    # Gradient is always reported for display, even when corroboration is absent.
    assert result.output["gradient_hpa"] == pytest.approx(1.0)


def test_bise_above_threshold_returns_75() -> None:
    plugin = BisePlugin(_config(min_hpa=1.5))
    pre = _prefetched(west_hpa=1013.0, east_hpa=1015.0)  # gradient = 2.0 ≥ 1.5
    result = plugin.score_window(
        window_times=[TS], prefetched=pre, contributing_models=["icon_d2"]
    )
    assert result.sub_score == pytest.approx(75.0)
    assert result.output["gradient_hpa"] == pytest.approx(2.0)


def test_bise_strong_gradient_returns_100() -> None:
    plugin = BisePlugin(_config(min_hpa=1.5))
    pre = _prefetched(west_hpa=1010.0, east_hpa=1013.5)  # gradient = 3.5 ≥ 3.0
    result = plugin.score_window(
        window_times=[TS], prefetched=pre, contributing_models=["icon_d2"]
    )
    assert result.sub_score == pytest.approx(100.0)
    assert result.output["gradient_hpa"] == pytest.approx(3.5)


def test_missing_pressure_data_opts_out() -> None:
    plugin = BisePlugin(_config())
    empty = BisePrefetched(west={}, east={})
    result = plugin.score_window(
        window_times=[TS], prefetched=empty, contributing_models=["icon_d2"]
    )
    assert result.sub_score is None
    assert result.output == {}


def test_disabled_plugin_reports_enabled_false() -> None:
    plugin = BisePlugin(_config(enabled=False))
    assert not plugin.enabled

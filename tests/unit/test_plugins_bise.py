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


def _config(*, enabled: bool = True, boost: bool = True, min_hpa: float = 1.5) -> BisePluginConfig:
    return BisePluginConfig(
        enabled=enabled,
        boost_if_bise=boost,
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


def test_bise_below_threshold_gives_no_boost() -> None:
    plugin = BisePlugin(_config(min_hpa=2.0))
    pre = _prefetched(west_hpa=1013.0, east_hpa=1014.0)  # gradient = 1.0 < 2.0
    boost, output = plugin.score_window(
        window_times=[TS], prefetched=pre, contributing_models=["icon_d2"]
    )
    assert boost == 0
    # gradient is always returned for display even when below threshold
    assert output["gradient_hpa"] == pytest.approx(1.0)


def test_bise_above_threshold_gives_plus_one() -> None:
    plugin = BisePlugin(_config(min_hpa=1.5))
    pre = _prefetched(west_hpa=1013.0, east_hpa=1015.0)  # gradient = 2.0 ≥ 1.5
    boost, output = plugin.score_window(
        window_times=[TS], prefetched=pre, contributing_models=["icon_d2"]
    )
    assert boost == 1
    assert output["gradient_hpa"] == pytest.approx(2.0)


def test_bise_strong_gradient_gives_plus_two() -> None:
    plugin = BisePlugin(_config(min_hpa=1.5))
    pre = _prefetched(west_hpa=1010.0, east_hpa=1013.5)  # gradient = 3.5 ≥ 3.0
    boost, output = plugin.score_window(
        window_times=[TS], prefetched=pre, contributing_models=["icon_d2"]
    )
    assert boost == 2
    assert output["gradient_hpa"] == pytest.approx(3.5)


def test_bise_boost_disabled_returns_zero_boost_but_keeps_output() -> None:
    plugin = BisePlugin(_config(boost=False))
    pre = _prefetched(west_hpa=1010.0, east_hpa=1015.0)  # gradient = 5.0
    boost, output = plugin.score_window(
        window_times=[TS], prefetched=pre, contributing_models=["icon_d2"]
    )
    assert boost == 0
    assert output["gradient_hpa"] == pytest.approx(5.0)


def test_missing_pressure_data_returns_empty() -> None:
    plugin = BisePlugin(_config())
    empty = BisePrefetched(west={}, east={})
    boost, output = plugin.score_window(
        window_times=[TS], prefetched=empty, contributing_models=["icon_d2"]
    )
    assert boost == 0
    assert output == {}


def test_disabled_plugin_reports_enabled_false() -> None:
    plugin = BisePlugin(_config(enabled=False))
    assert not plugin.enabled

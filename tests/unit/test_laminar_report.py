from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from parames.domain import HourForecast
from parames.plugins.laminar import LaminarPlugin, LaminarPluginConfig, LaminarPrefetched

ZURICH = ZoneInfo("Europe/Zurich")
TS = datetime(2026, 4, 29, 12, 0, tzinfo=ZURICH)
TS4 = [TS + timedelta(hours=i) for i in range(4)]


def _config(**kwargs) -> LaminarPluginConfig:
    return LaminarPluginConfig(**kwargs)


def _hour(
    ts: datetime,
    *,
    wind_speed: float = 20.0,
    wind_direction: float = 60.0,
    wind_gusts: float = 24.0,
    precipitation: float = 0.0,
    showers: float = 0.0,
    cape: float = 10.0,
    pressure_msl: float = 1015.0,
) -> HourForecast:
    return HourForecast(
        time=ts,
        wind_speed=wind_speed,
        wind_direction=wind_direction,
        wind_gusts=wind_gusts,
        precipitation=precipitation,
        showers=showers,
        cape=cape,
        pressure_msl=pressure_msl,
    )


def _score(
    cfg=None,
    hours=None,
    secondary_hours=None,
    window_times=None,
    contributing_models=None,
    primary_model="icon_d2",
    secondary_model="ecmwf_ifs",
):
    if cfg is None:
        cfg = _config()
    if hours is None:
        hours = {TS: _hour(TS)}
    if window_times is None:
        window_times = [TS]
    if contributing_models is None:
        contributing_models = [primary_model]
        if secondary_hours is not None:
            contributing_models = [primary_model, secondary_model]
    data = {primary_model: hours}
    if secondary_hours is not None:
        data[secondary_model] = secondary_hours
    pre = LaminarPrefetched(data=data)
    plugin = LaminarPlugin(cfg)
    return plugin.score_window(
        window_times=window_times,
        prefetched=pre,
        contributing_models=contributing_models,
    )


# ── Report presence ──────────────────────────────────────────────────────────

def test_laminar_report_present_on_success() -> None:
    result = _score()
    assert result.report is not None
    assert result.report.type == "laminar"


def test_laminar_report_present_on_unavailable() -> None:
    hours = {TS: HourForecast(time=TS, wind_speed=None, wind_direction=60.0, wind_gusts=24.0)}
    result = _score(hours=hours)
    assert result.sub_score is None
    assert result.report is not None


# ── Rule presence and delta ──────────────────────────────────────────────────

def test_gust_factor_rule_pass() -> None:
    result = _score(hours={TS: _hour(TS, wind_speed=20.0, wind_gusts=24.0)})
    rules = {r.name: r for r in result.report.rules}
    assert "gust_factor" in rules
    assert rules["gust_factor"].outcome == "pass"
    assert rules["gust_factor"].delta == 0.0


def test_gust_factor_rule_warn_delta_10() -> None:
    result = _score(hours={TS: _hour(TS, wind_speed=20.0, wind_gusts=30.0)})  # gf=1.5
    rules = {r.name: r for r in result.report.rules}
    assert rules["gust_factor"].outcome == "warn"
    assert rules["gust_factor"].delta == pytest.approx(-10.0)


def test_gust_factor_rule_fail_delta_35() -> None:
    result = _score(hours={TS: _hour(TS, wind_speed=20.0, wind_gusts=40.0)})  # gf=2.0
    rules = {r.name: r for r in result.report.rules}
    assert rules["gust_factor"].outcome == "fail"
    assert rules["gust_factor"].delta == pytest.approx(-35.0)


def test_direction_variability_rule_present() -> None:
    result = _score()
    rules = {r.name: r for r in result.report.rules}
    assert "direction_variability" in rules


def test_speed_range_rule_present() -> None:
    result = _score()
    rules = {r.name: r for r in result.report.rules}
    assert "speed_range" in rules


def test_cape_availability_rule_present() -> None:
    result = _score()
    rules = {r.name: r for r in result.report.rules}
    assert "cape_availability" in rules


def test_cape_rule_present_when_data_available() -> None:
    result = _score(hours={TS: _hour(TS, cape=100.0)})
    rules = {r.name: r for r in result.report.rules}
    assert "cape" in rules
    assert rules["cape"].outcome == "warn"
    assert rules["cape"].delta == pytest.approx(-7.0)


def test_precipitation_rule_fail_delta_15() -> None:
    result = _score(hours={TS: _hour(TS, precipitation=0.5)})
    rules = {r.name: r for r in result.report.rules}
    assert rules["precipitation"].outcome == "fail"
    assert rules["precipitation"].delta == pytest.approx(-15.0)


def test_showers_rule_fail_delta_15() -> None:
    result = _score(hours={TS: _hour(TS, showers=0.3)})
    rules = {r.name: r for r in result.report.rules}
    assert rules["showers"].outcome == "fail"
    assert rules["showers"].delta == pytest.approx(-15.0)


def test_pressure_tendency_rule_present() -> None:
    ts_3h = TS + timedelta(hours=3)
    hours = {
        TS: _hour(TS, pressure_msl=1015.0),
        ts_3h: _hour(ts_3h, pressure_msl=1015.5),
    }
    result = _score(hours=hours, window_times=[TS])
    rules = {r.name: r for r in result.report.rules}
    assert "pressure_tendency" in rules
    assert rules["pressure_tendency"].outcome == "pass"


def test_model_agreement_rule_present_with_secondary() -> None:
    primary = {TS: _hour(TS, wind_direction=60.0, wind_speed=20.0)}
    secondary = {TS: _hour(TS, wind_direction=62.0, wind_speed=21.0)}
    result = _score(hours=primary, secondary_hours=secondary)
    rules = {r.name: r for r in result.report.rules}
    assert "model_agreement" in rules
    assert rules["model_agreement"].outcome == "pass"


def test_primary_and_secondary_resolution_rules_present() -> None:
    result = _score()
    rule_names = [r.name for r in result.report.rules]
    assert "primary_model_resolution" in rule_names
    assert "secondary_model_resolution" in rule_names


# ── Hourly trace ─────────────────────────────────────────────────────────────

def test_hourly_trace_populated() -> None:
    hours = {ts: _hour(ts) for ts in TS4}
    result = _score(hours=hours, window_times=TS4)
    assert result.report is not None
    assert len(result.report.hourly) == 4
    for entry in result.report.hourly:
        assert "time" in entry
        assert "gust_factor" in entry
        assert "gust_spread_kmh" in entry
        assert "primary" in entry


def test_hourly_trace_includes_secondary_when_present() -> None:
    primary = {TS: _hour(TS)}
    secondary = {TS: _hour(TS, wind_speed=21.0)}
    result = _score(hours=primary, secondary_hours=secondary)
    assert result.report is not None
    entry = result.report.hourly[0]
    assert "secondary" in entry


# ── Metrics and config snapshot ──────────────────────────────────────────────

def test_metrics_populated() -> None:
    result = _score()
    assert result.report is not None
    assert "avg_gust_factor" in result.report.metrics
    assert "direction_variability_deg" in result.report.metrics
    assert "speed_range_kmh" in result.report.metrics


def test_config_snapshot_present() -> None:
    result = _score()
    assert result.report is not None
    assert result.report.config_snapshot


# ── Output dict unchanged ────────────────────────────────────────────────────

def test_output_keys_unchanged() -> None:
    result = _score()
    out = result.output
    assert "score" in out
    assert "label" in out
    assert "reasons" in out
    assert "metrics" in out
    assert "primary_model" in out
    assert "secondary_model" in out

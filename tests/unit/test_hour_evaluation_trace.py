from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from parames.config import ModelAgreementConfig
from parames.domain import HourForecast
from parames.evaluation.wind import evaluate_hour_reasons
from parames.evaluation.core import _evaluate_timestamp
from parames.config import WindConfig, TimeWindowConfig

ZURICH = ZoneInfo("Europe/Zurich")
TS = datetime(2026, 4, 29, 12, 0, tzinfo=ZURICH)


# ── evaluate_hour_reasons unit tests ────────────────────────────────────────

def _wind(min_speed=10.0, strong_speed=28.0, dir_min=30.0, dir_max=100.0, min_consecutive=2):
    return WindConfig(
        min_speed_kmh=min_speed,
        strong_speed_kmh=strong_speed,
        direction_min_deg=dir_min,
        direction_max_deg=dir_max,
        min_consecutive_hours=min_consecutive,
    )


def test_hour_passes_no_reasons() -> None:
    hour = HourForecast(time=TS, wind_speed=15.0, wind_direction=60.0)
    passed, reasons = evaluate_hour_reasons(hour, wind=_wind(), time_window=None, dry=None)
    assert passed
    assert reasons == []


def test_out_of_time_window() -> None:
    hour = HourForecast(time=TS.replace(hour=7), wind_speed=15.0, wind_direction=60.0)
    tw = TimeWindowConfig(start_hour=9, end_hour=20)
    passed, reasons = evaluate_hour_reasons(hour, wind=_wind(), time_window=tw, dry=None)
    assert not passed
    assert "out_of_time_window" in reasons


def test_wind_below_min() -> None:
    hour = HourForecast(time=TS, wind_speed=5.0, wind_direction=60.0)
    passed, reasons = evaluate_hour_reasons(hour, wind=_wind(min_speed=10.0), time_window=None, dry=None)
    assert not passed
    assert "wind_below_min" in reasons


def test_wind_speed_none_gives_wind_below_min() -> None:
    hour = HourForecast(time=TS, wind_speed=None, wind_direction=60.0)
    passed, reasons = evaluate_hour_reasons(hour, wind=_wind(), time_window=None, dry=None)
    assert not passed
    assert "wind_below_min" in reasons


def test_wind_direction_out_of_range() -> None:
    hour = HourForecast(time=TS, wind_speed=15.0, wind_direction=200.0)
    passed, reasons = evaluate_hour_reasons(hour, wind=_wind(dir_min=30.0, dir_max=100.0), time_window=None, dry=None)
    assert not passed
    assert "wind_direction_out_of_range" in reasons


def test_evaluate_hour_candidate_delegates_to_reasons() -> None:
    from parames.evaluation.wind import evaluate_hour_candidate
    hour = HourForecast(time=TS, wind_speed=15.0, wind_direction=60.0)
    assert evaluate_hour_candidate(hour, wind=_wind(), time_window=None, dry=None) is True


# ── _evaluate_timestamp integration tests ───────────────────────────────────

def _profile_with_agreement(min_models=2, required=True, default_config=None):
    if default_config is not None:
        return default_config.alerts[0]
    from parames.config import AlertProfileConfig, WindConfig, ModelAgreementConfig, LocationConfig
    return AlertProfileConfig(
        name="test",
        location=LocationConfig(name="zurich", latitude=47.4, longitude=8.5),
        models=["icon_ch2", "icon_d2"],
        wind=WindConfig(
            min_speed_kmh=10.0,
            strong_speed_kmh=28.0,
            direction_min_deg=30.0,
            direction_max_deg=100.0,
            min_consecutive_hours=2,
        ),
        model_agreement=ModelAgreementConfig(
            required=required,
            min_models_matching=min_models,
            max_direction_delta_deg=35.0,
            max_speed_delta_kmh=8.0,
        ),
        delivery=["telegram"],
    )


def _make_forecast(ts, speed=15.0, direction=60.0):
    return HourForecast(time=ts, wind_speed=speed, wind_direction=direction)


def test_accepted_hour_has_no_rejection_reasons(default_config) -> None:
    profile = default_config.alerts[0]
    forecasts = {
        model: {TS: _make_forecast(TS)}
        for model in profile.models
    }
    evaluated, hour_eval = _evaluate_timestamp(
        timestamp=TS,
        profile=profile,
        model_forecasts=forecasts,
    )
    assert evaluated is not None
    assert hour_eval.accepted is True
    assert hour_eval.rejection_reasons == []
    assert sorted(hour_eval.matching_models) == sorted(profile.models)


def test_min_models_not_met(default_config) -> None:
    profile = default_config.alerts[0]
    # Only one model has valid data; min_models_matching=2
    forecasts = {
        profile.models[0]: {TS: _make_forecast(TS)},
        profile.models[1]: {},  # missing
    }
    evaluated, hour_eval = _evaluate_timestamp(
        timestamp=TS,
        profile=profile,
        model_forecasts=forecasts,
    )
    assert evaluated is None
    assert hour_eval.accepted is False
    assert "min_models_matching_not_met" in hour_eval.rejection_reasons


def test_model_agreement_failed(default_config) -> None:
    profile = default_config.alerts[0]
    forecasts = {
        profile.models[0]: {TS: _make_forecast(TS, direction=40.0, speed=15.0)},
        profile.models[1]: {TS: _make_forecast(TS, direction=120.0, speed=15.0)},  # 80° apart
    }
    evaluated, hour_eval = _evaluate_timestamp(
        timestamp=TS,
        profile=profile,
        model_forecasts=forecasts,
    )
    assert evaluated is None
    assert hour_eval.accepted is False
    assert "model_agreement_failed" in hour_eval.rejection_reasons


def test_wind_below_min_rejects_model(default_config) -> None:
    profile = default_config.alerts[0]
    # Both models have data but wind is too slow
    forecasts = {
        model: {TS: HourForecast(time=TS, wind_speed=3.0, wind_direction=60.0)}
        for model in profile.models
    }
    evaluated, hour_eval = _evaluate_timestamp(
        timestamp=TS,
        profile=profile,
        model_forecasts=forecasts,
    )
    assert evaluated is None
    assert hour_eval.accepted is False
    assert "min_models_matching_not_met" in hour_eval.rejection_reasons


def test_evaluate_timestamp_matching_models_populated(default_config) -> None:
    profile = default_config.alerts[0]
    forecasts = {
        model: {TS: _make_forecast(TS)}
        for model in profile.models
    }
    _, hour_eval = _evaluate_timestamp(
        timestamp=TS, profile=profile, model_forecasts=forecasts
    )
    assert set(hour_eval.matching_models) == set(profile.models)

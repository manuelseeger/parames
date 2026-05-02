from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from parames.domain import HourForecast
from parames.evaluation import (
    EvaluatedHour,
    angular_distance,
    build_candidate_windows,
    direction_in_range,
    evaluate,
    evaluate_hour_candidate,
    models_agree,
    score_window,
    vector_average_direction,
)
from snapshot_fixtures import SnapshotForecastClient


FIXTURE_DIR = Path("tests/fixtures/open_meteo/zurich_bise_positive")


def test_direction_in_range_handles_wrap() -> None:
    assert direction_in_range(10, 350, 30)
    assert direction_in_range(355, 350, 30)
    assert not direction_in_range(200, 350, 30)


def test_angular_distance_is_circular() -> None:
    assert angular_distance(350, 10) == 20
    assert angular_distance(0, 180) == 180


def test_vector_average_direction_wraps() -> None:
    average = vector_average_direction([350, 10])
    assert average in {0.0, 360.0}


def test_evaluate_hour_candidate_accepts_valid_hour(default_config, fixed_now) -> None:
    profile = default_config.alerts[0]
    hour = HourForecast(
        time=fixed_now.replace(hour=12),
        wind_speed=11.0,  # >= min_speed_kmh 10.0
        wind_direction=50.0,  # in range [30, 100]
        precipitation=0.0,
    )

    assert evaluate_hour_candidate(
        hour,
        wind=profile.wind,
        time_window=profile.time_window,
        dry=profile.dry,
    )


def test_evaluate_hour_candidate_does_not_reject_on_precipitation(default_config, fixed_now) -> None:
    """evaluate_hour_candidate does not filter on precipitation; that's done upstream."""
    profile = default_config.alerts[0]
    hour = HourForecast(
        time=fixed_now.replace(hour=12),
        wind_speed=11.0,
        wind_direction=50.0,
        precipitation=2.5,
    )

    assert evaluate_hour_candidate(
        hour,
        wind=profile.wind,
        time_window=profile.time_window,
        dry=profile.dry,
    )


def test_models_agree_rejects_large_delta(default_config, fixed_now) -> None:
    agreement = default_config.alerts[0].model_agreement
    assert agreement is not None
    left = HourForecast(time=fixed_now, wind_speed=9.0, wind_direction=40.0)
    right = HourForecast(time=fixed_now, wind_speed=20.0, wind_direction=120.0)
    assert not models_agree([left, right], agreement)


def test_build_candidate_windows_filters_short_runs(default_config, fixed_now) -> None:
    profile = default_config.alerts[0]
    hours = [
        EvaluatedHour(
            time=fixed_now,
            avg_wind_speed_kmh=9.0,
            max_wind_speed_kmh=12.0,
            avg_direction_deg=60.0,
            models=("icon_ch2", "icon_d2"),
            avg_precipitation_mm_per_hour=0.0,
        ),
        EvaluatedHour(
            time=fixed_now + timedelta(hours=1),
            avg_wind_speed_kmh=10.0,
            max_wind_speed_kmh=13.0,
            avg_direction_deg=70.0,
            models=("icon_ch2", "icon_d2"),
            avg_precipitation_mm_per_hour=0.1,
        ),
        EvaluatedHour(
            time=fixed_now + timedelta(hours=2),
            avg_wind_speed_kmh=11.0,
            max_wind_speed_kmh=13.5,
            avg_direction_deg=75.0,
            models=("icon_ch2", "icon_d2"),
            avg_precipitation_mm_per_hour=0.0,
        ),
        EvaluatedHour(
            time=fixed_now + timedelta(hours=4),
            avg_wind_speed_kmh=12.0,
            max_wind_speed_kmh=14.0,
            avg_direction_deg=80.0,
            models=("icon_ch2", "icon_d2"),
            avg_precipitation_mm_per_hour=0.2,
        ),
    ]

    windows = build_candidate_windows(profile, hours)
    assert len(windows) == 1
    assert windows[0].duration_hours == 3


def _hours(fixed_now, *, count: int, speed: float):
    return [
        EvaluatedHour(
            time=fixed_now + timedelta(hours=index),
            avg_wind_speed_kmh=speed,
            max_wind_speed_kmh=speed + 0.5,
            avg_direction_deg=60.0,
            models=("icon_ch2", "icon_d2"),
            avg_precipitation_mm_per_hour=0.0,
        )
        for index in range(count)
    ]


@pytest.mark.parametrize(
    "speed,count,expected_classification",
    [
        # wind_speed sub-score: tent(min=10, strong=28, peak=19)
        # wind_duration sub-score: 0 if <2, 50 at 2, 75 at 3, 100 at 4+
        (10.0, 2, "weak"),       # speed=0, dur=50 → 25
        (12.0, 4, "candidate"),  # speed≈22, dur=100 → 61
        (16.0, 4, "strong"),     # speed≈67, dur=100 → 83
        (19.0, 4, "excellent"),  # speed=100, dur=100 → 100
    ],
)
def test_score_window_tier_boundaries(default_config, fixed_now, speed, count, expected_classification) -> None:
    profile = default_config.alerts[0].model_copy(update={"dry": None, "plugins": []})
    window = score_window(profile, _hours(fixed_now, count=count, speed=speed))
    assert window.classification == expected_classification


def test_score_window_returns_unavailable_when_all_signals_opt_out(default_config, fixed_now) -> None:
    """An aggregator with zero-weight built-ins and no plugins yields score=None."""
    from parames.config import ScoringConfig, ScoringWeightsConfig

    profile = default_config.alerts[0].model_copy(update={"dry": None, "plugins": []})
    scoring = ScoringConfig(weights=ScoringWeightsConfig(wind_speed=0.0, wind_duration=0.0, plugins={}))
    window = score_window(profile, _hours(fixed_now, count=4, speed=11.0), scoring=scoring)
    assert window.score is None
    assert window.classification == "unavailable"


def test_score_window_renormalizes_when_plugin_opts_out(default_config, fixed_now) -> None:
    """A plugin that returns None is excluded from both numerator and denominator."""
    from typing import Any

    profile = default_config.alerts[0].model_copy(update={"dry": None, "plugins": []})
    hours = _hours(fixed_now, count=4, speed=11.0)

    class _NoneBisePlugin:
        type = "bise"
        enabled = True
        def prefetch(self, **_): return None
        def score_window(self, **_) -> tuple[float | None, dict[str, Any]]:
            return None, {}

    baseline = score_window(profile, hours)
    with_opt_out = score_window(profile, hours, plugins=[_NoneBisePlugin()])
    # Plugin opting out doesn't move the score — same as baseline.
    assert baseline.score == with_opt_out.score
    assert with_opt_out.subscores["bise"] is None


def test_evaluate_positive_snapshot_replays_expected_window(default_config) -> None:
    profile = next(a for a in default_config.alerts if a.name == "zurich_bise")
    snapshot_client = SnapshotForecastClient(FIXTURE_DIR)
    now = snapshot_client.captured_at

    try:
        windows = evaluate(profile, client=snapshot_client, now=now, scoring=default_config.scoring)
    finally:
        snapshot_client.close()

    assert len(windows) == 1
    window = windows[0]
    expected = snapshot_client.expected_windows[0]
    assert window.alert_name == expected["alert_name"]
    assert window.start.isoformat() == expected["start"]
    assert window.end.isoformat() == expected["end"]
    assert window.duration_hours == expected["duration_hours"]
    assert window.models == expected["models"]
    assert window.score == expected["score"]
    assert window.classification == expected["classification"]
    assert window.avg_wind_speed_kmh == pytest.approx(expected["avg_wind_speed_kmh"])
    assert window.max_wind_speed_kmh == pytest.approx(expected["max_wind_speed_kmh"])
    assert window.avg_direction_deg == pytest.approx(expected["avg_direction_deg"])
    assert window.plugin_outputs["bise"]["gradient_hpa"] == pytest.approx(expected["bise_pressure_gradient_hpa"])

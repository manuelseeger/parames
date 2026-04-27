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


def test_evaluate_hour_candidate_checks_filters(default_config, fixed_now) -> None:
    profile = default_config.alerts[0]
    hour = HourForecast(
        time=fixed_now.replace(hour=12),
        wind_speed=9.0,
        wind_direction=50.0,
        precipitation=0.0,
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
            precipitation_ok=True,
            bise_gradient_hpa=2.0,
        ),
        EvaluatedHour(
            time=fixed_now + timedelta(hours=1),
            avg_wind_speed_kmh=10.0,
            max_wind_speed_kmh=13.0,
            avg_direction_deg=70.0,
            models=("icon_ch2", "icon_d2"),
            precipitation_ok=True,
            bise_gradient_hpa=2.0,
        ),
        EvaluatedHour(
            time=fixed_now + timedelta(hours=3),
            avg_wind_speed_kmh=12.0,
            max_wind_speed_kmh=14.0,
            avg_direction_deg=80.0,
            models=("icon_ch2", "icon_d2"),
            precipitation_ok=True,
            bise_gradient_hpa=2.0,
        ),
    ]

    windows = build_candidate_windows(profile, hours)
    assert len(windows) == 1
    assert windows[0].duration_hours == 2


def test_score_window_classification_boundaries(default_config, fixed_now) -> None:
    profile = default_config.alerts[0].model_copy(
        update={"dry": None, "bise": None}
    )
    hours = [
        EvaluatedHour(
            time=fixed_now + timedelta(hours=index),
            avg_wind_speed_kmh=10.5,
            max_wind_speed_kmh=11.0,
            avg_direction_deg=60.0,
            models=("icon_ch2", "icon_d2"),
            precipitation_ok=True,
            bise_gradient_hpa=None,
        )
        for index in range(4)
    ]

    window = score_window(profile, hours)
    assert window.score == 4
    assert window.classification == "candidate"


def test_evaluate_positive_snapshot_replays_expected_window(default_config) -> None:
    profile = default_config.alerts[0]
    snapshot_client = SnapshotForecastClient(FIXTURE_DIR)
    now = snapshot_client.captured_at

    try:
        windows = evaluate(profile, client=snapshot_client, now=now)
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
    assert window.bise_pressure_gradient_hpa == pytest.approx(expected["bise_pressure_gradient_hpa"])

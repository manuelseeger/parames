from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from parames.evaluation import evaluate
from parames.forecast import ForecastClientError, OpenMeteoForecastClient


@pytest.mark.integration
def test_single_location_fetch_returns_hourly_data(default_config) -> None:
    profile = default_config.alerts[0]
    with OpenMeteoForecastClient() as client:
        hourly = client.fetch_hourly_forecast(
            location=profile.location,
            model=profile.models[0],
            hourly_variables=[
                f"wind_speed_{profile.wind_level_m}m",
                f"wind_direction_{profile.wind_level_m}m",
                "precipitation",
            ],
        )

    assert hourly
    sample = next(iter(hourly.values()))
    assert sample.wind_speed is None or 0 <= sample.wind_speed <= 200
    assert sample.wind_direction is None or 0 <= sample.wind_direction <= 360


@pytest.mark.integration
def test_invalid_model_id_propagates_error(default_config) -> None:
    profile = default_config.alerts[0]
    with OpenMeteoForecastClient() as client:
        with pytest.raises(ForecastClientError):
            client.fetch_hourly_forecast(
                location=profile.location,
                model="bogus_model_name",
                hourly_variables=[f"wind_speed_{profile.wind_level_m}m"],
            )


@pytest.mark.integration
def test_evaluate_end_to_end_with_live_api(default_config) -> None:
    profile = default_config.alerts[0]
    now = datetime.now(ZoneInfo("Europe/Zurich"))
    with OpenMeteoForecastClient() as client:
        windows = evaluate(profile, client=client, now=now)

    assert isinstance(windows, list)
    for window in windows:
        assert window.score is None or 0 <= window.score <= 100
        assert window.start < window.end
        assert window.classification in {"weak", "candidate", "strong", "excellent", "unavailable"}
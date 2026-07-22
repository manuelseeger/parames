from __future__ import annotations

import httpx

from parames.common import LocationConfig
from parames.forecast import OpenMeteoForecastClient


def test_retries_open_meteo_overload_before_returning_forecast() -> None:
    calls = 0
    delays: list[float] = []

    def responder(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"error": True, "reason": "The service is overloaded"})
        return httpx.Response(
            200,
            json={
                "hourly": {
                    "time": ["2026-07-22T16:00"],
                    "wind_speed_10m": [12.0],
                    "wind_direction_10m": [180.0],
                }
            },
        )

    client = httpx.Client(
        base_url="https://api.open-meteo.com/v1/forecast",
        transport=httpx.MockTransport(responder),
    )
    forecast_client = OpenMeteoForecastClient(client=client, sleep=delays.append)

    result = forecast_client.fetch_hourly_forecast(
        location=LocationConfig(name="Test", latitude=47.0, longitude=7.0),
        model="icon_eu",
        hourly_variables=["wind_speed_10m", "wind_direction_10m"],
    )

    assert calls == 2
    assert delays == [1]
    assert next(iter(result.values())).wind_speed == 12.0

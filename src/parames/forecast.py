from __future__ import annotations

import ssl
from collections.abc import Iterable
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

import certifi
import httpx

from parames.common import LocationConfig
from parames.domain import HourForecast

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
ZURICH_TIMEZONE = "Europe/Zurich"
LEGACY_MODEL_ALIASES = {
    "icon_ch1": "meteoswiss_icon_ch1",
    "icon_ch2": "meteoswiss_icon_ch2",
}


class ForecastClient(Protocol):
    def fetch_hourly_forecast(
        self,
        *,
        location: LocationConfig,
        model: str,
        hourly_variables: Iterable[str],
        forecast_days: int = 3,
        timezone: str = ZURICH_TIMEZONE,
    ) -> dict[datetime, HourForecast]: ...

    def close(self) -> None: ...


def _create_default_ssl_context() -> ssl.SSLContext:
    """Create a default SSL context with certifi CA bundle."""
    return ssl.create_default_context(cafile=certifi.where())


class ForecastClientError(RuntimeError):
    pass


class OpenMeteoForecastClient:
    def __init__(
        self,
        *,
        base_url: str = OPEN_METEO_URL,
        timeout: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=base_url,
            timeout=timeout,
            verify=_create_default_ssl_context(),
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "OpenMeteoForecastClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def fetch_hourly_forecast(
        self,
        *,
        location: LocationConfig,
        model: str,
        hourly_variables: Iterable[str],
        forecast_days: int = 3,
        timezone: str = ZURICH_TIMEZONE,
    ) -> dict[datetime, HourForecast]:
        resolved_model = LEGACY_MODEL_ALIASES.get(model, model)
        response = self._client.get(
            "",
            params={
                "latitude": location.latitude,
                "longitude": location.longitude,
                "hourly": ",".join(hourly_variables),
                "models": resolved_model,
                "forecast_days": forecast_days,
                "timezone": timezone,
                "wind_speed_unit": "kmh",
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ForecastClientError(response.text) from exc

        payload = response.json()
        if payload.get("error"):
            raise ForecastClientError(str(payload.get("reason") or payload["error"]))

        return self._normalize_hourly_payload(payload, timezone)

    def _normalize_hourly_payload(
        self, payload: dict[str, object], timezone: str
    ) -> dict[datetime, HourForecast]:
        hourly = payload.get("hourly")
        if not isinstance(hourly, dict):
            raise ForecastClientError("Open-Meteo response is missing hourly data")

        raw_times = hourly.get("time")
        if not isinstance(raw_times, list):
            raise ForecastClientError("Open-Meteo response is missing hourly.time")

        tz = ZoneInfo(timezone)
        result: dict[datetime, HourForecast] = {}
        for index, raw_time in enumerate(raw_times):
            if not isinstance(raw_time, str):
                raise ForecastClientError("Unexpected timestamp in hourly.time")
            stamp = datetime.fromisoformat(raw_time).replace(tzinfo=tz)
            forecast = HourForecast(time=stamp)
            for field_name, source_key in (
                ("wind_speed", self._find_hourly_key(hourly, "wind_speed_")),
                ("wind_direction", self._find_hourly_key(hourly, "wind_direction_")),
                ("precipitation", "precipitation"),
                ("pressure_msl", "pressure_msl"),
                ("wind_gusts", self._find_hourly_key(hourly, "wind_gusts_")),
                ("cape", "cape"),
                ("showers", "showers"),
            ):
                series = hourly.get(source_key) if source_key else None
                value = series[index] if isinstance(series, list) and index < len(series) else None
                setattr(forecast, field_name, float(value) if value is not None else None)
            result[stamp] = forecast
        return result

    @staticmethod
    def _find_hourly_key(hourly: dict[str, object], prefix: str) -> str | None:
        for key in hourly:
            if key.startswith(prefix):
                return key
        return None

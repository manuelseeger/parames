from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from parames.config import LocationConfig
from parames.domain import HourForecast
from parames.forecast import OpenMeteoForecastClient, ZURICH_TIMEZONE


class SnapshotForecastClient:
    def __init__(self, fixture_dir: Path) -> None:
        metadata = json.loads((fixture_dir / "metadata.json").read_text(encoding="utf-8"))
        self.metadata: dict[str, Any] = metadata
        self._payloads = {
            request["name"]: json.loads(
                (fixture_dir / f"{request['name']}.json").read_text(encoding="utf-8")
            )
            for request in metadata["requests"]
        }
        self._normalizer = OpenMeteoForecastClient()

    @property
    def captured_at(self) -> datetime:
        return datetime.fromisoformat(self.metadata["captured_at"])

    @property
    def expected_windows(self) -> list[dict[str, Any]]:
        return self.metadata["expected_windows"]

    def close(self) -> None:
        self._normalizer.close()

    def fetch_hourly_forecast(
        self,
        *,
        location: LocationConfig,
        model: str,
        hourly_variables: Iterable[str],
        forecast_days: int = 3,
        timezone: str = ZURICH_TIMEZONE,
    ) -> dict[datetime, HourForecast]:
        del forecast_days
        variables = list(hourly_variables)
        for request in self.metadata["requests"]:
            if (
                request["location"]["name"] == location.name
                and request["model"] == model
                and request["hourly_variables"] == variables
            ):
                payload = self._payloads[request["name"]]
                return self._normalizer._normalize_hourly_payload(payload, timezone)
        raise AssertionError(
            f"Unexpected forecast request: {location.name=} {model=} {hourly_variables=}"
        )

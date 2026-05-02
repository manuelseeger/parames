from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import click
import httpx

from parames.common import LocationConfig
from parames.config import load_app_config
from parames.domain import HourForecast
from parames.evaluation import evaluate
from parames.forecast import (
    LEGACY_MODEL_ALIASES,
    OpenMeteoForecastClient,
    ZURICH_TIMEZONE,
    _create_default_ssl_context,
)
from parames.plugins.bise import BisePluginConfig
from parames.plugins.laminar import LaminarPluginConfig

OPEN_METEO_HISTORICAL_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"


def _build_requests(profile) -> list[dict[str, object]]:
    hourly_variables = [
        f"wind_speed_{profile.wind_level_m}m",
        f"wind_direction_{profile.wind_level_m}m",
        "precipitation",
        "pressure_msl",
    ]
    bise = next(
        (p for p in profile.plugins if isinstance(p, BisePluginConfig) and p.enabled),
        None,
    )
    laminar = next(
        (p for p in profile.plugins if isinstance(p, LaminarPluginConfig) and p.enabled),
        None,
    )
    requests: list[dict[str, object]] = []
    for model in profile.models:
        requests.append(
            {
                "name": f"alert_{model}",
                "location": profile.location.model_dump(),
                "model": model,
                "hourly_variables": hourly_variables,
            }
        )
        if laminar:
            level = laminar.wind_level_m
            requests.append(
                {
                    "name": f"laminar_{model}",
                    "location": profile.location.model_dump(),
                    "model": model,
                    "hourly_variables": [
                        f"wind_speed_{level}m",
                        f"wind_direction_{level}m",
                        f"wind_gusts_{level}m",
                        "precipitation",
                        "showers",
                        "cape",
                        "pressure_msl",
                    ],
                }
            )
        if bise:
            requests.append(
                {
                    "name": f"west_{model}",
                    "location": bise.pressure_reference_west.model_dump(),
                    "model": model,
                    "hourly_variables": ["pressure_msl"],
                }
            )
            requests.append(
                {
                    "name": f"east_{model}",
                    "location": bise.pressure_reference_east.model_dump(),
                    "model": model,
                    "hourly_variables": ["pressure_msl"],
                }
            )
    return requests


def _fetch_live_payloads(requests: list[dict[str, object]]) -> dict[str, dict]:
    payloads: dict[str, dict] = {}
    with OpenMeteoForecastClient() as client:
        for request in requests:
            location = request["location"]
            model = str(request["model"])
            response = client._client.get(
                "",
                params={
                    "latitude": location["latitude"],
                    "longitude": location["longitude"],
                    "hourly": ",".join(request["hourly_variables"]),
                    "models": LEGACY_MODEL_ALIASES.get(model, model),
                    "forecast_days": 3,
                    "timezone": ZURICH_TIMEZONE,
                    "wind_speed_unit": "kmh",
                },
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("error"):
                raise click.ClickException(str(payload.get("reason") or payload["error"]))
            payloads[request["name"]] = payload
    return payloads


def _fetch_historical_payloads(
    requests: list[dict[str, object]], target_date: date
) -> dict[str, dict]:
    payloads: dict[str, dict] = {}
    end_date = target_date + timedelta(days=2)
    with httpx.Client(
        base_url=OPEN_METEO_HISTORICAL_URL,
        timeout=20.0,
        verify=_create_default_ssl_context(),
    ) as client:
        for request in requests:
            location = request["location"]
            model = str(request["model"])
            response = client.get(
                "",
                params={
                    "latitude": location["latitude"],
                    "longitude": location["longitude"],
                    "hourly": ",".join(request["hourly_variables"]),
                    "models": LEGACY_MODEL_ALIASES.get(model, model),
                    "start_date": target_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "timezone": ZURICH_TIMEZONE,
                    "wind_speed_unit": "kmh",
                },
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("error"):
                raise click.ClickException(str(payload.get("reason") or payload["error"]))
            payloads[request["name"]] = payload
    return payloads


class _ReplayClient:
    """Replays captured payloads through the normalizer so evaluate() needs no network calls."""

    def __init__(
        self,
        payloads: dict[str, dict],
        requests: list[dict],
        normalizer: OpenMeteoForecastClient,
    ) -> None:
        self._payloads = payloads
        self._requests = requests
        self._normalizer = normalizer

    def fetch_hourly_forecast(
        self,
        *,
        location: LocationConfig,
        model: str,
        hourly_variables: list[str],
        forecast_days: int = 3,
        timezone: str = ZURICH_TIMEZONE,
    ) -> dict[datetime, HourForecast]:
        del forecast_days
        for request in self._requests:
            if (
                request["location"]["name"] == location.name
                and request["model"] == model
                and request["hourly_variables"] == hourly_variables
            ):
                return self._normalizer._normalize_hourly_payload(
                    self._payloads[request["name"]], timezone
                )
        raise AssertionError(
            f"No captured payload for {location.name=} {model=} {hourly_variables=}"
        )


def _capture_profile(profile, target_date: date, is_historical: bool) -> None:
    fixture_dir = (
        Path("tests/fixtures/open_meteo") / f"{profile.name}_{target_date.isoformat()}"
    )
    fixture_dir.mkdir(parents=True, exist_ok=True)

    captured_at = datetime(
        target_date.year, target_date.month, target_date.day, 12, 0,
        tzinfo=ZoneInfo(ZURICH_TIMEZONE),
    )
    requests = _build_requests(profile)

    if is_historical:
        payloads = _fetch_historical_payloads(requests, target_date)
    else:
        payloads = _fetch_live_payloads(requests)

    for name, payload in payloads.items():
        (fixture_dir / f"{name}.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

    with OpenMeteoForecastClient() as normalizer:
        replay_client = _ReplayClient(payloads, requests, normalizer)
        windows = evaluate(profile, client=replay_client, now=captured_at)

    metadata = {
        "captured_at": captured_at.isoformat(),
        "timezone": ZURICH_TIMEZONE,
        "profile_name": profile.name,
        "requests": requests,
        "expected_windows": [window.model_dump(mode="json") for window in windows],
    }
    (fixture_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )

    click.echo(f"Saved snapshot to {fixture_dir}")
    click.echo(json.dumps(metadata["expected_windows"], indent=2))


@click.command("capture")
@click.option(
    "--date",
    "target_date",
    default=None,
    metavar="YYYY-MM-DD",
    help="Date to capture. Defaults to today. Past dates use the historical forecast API.",
    type=click.DateTime(formats=["%Y-%m-%d"]),
)
@click.option(
    "--config",
    "config_path",
    default=Path("config/default.yaml"),
    show_default=True,
    type=click.Path(path_type=Path, dir_okay=False),
    help="Path to the YAML configuration file.",
)
@click.option(
    "--alert",
    "alert_name",
    default=None,
    help="Alert profile name to capture. Captures all configured alerts if omitted.",
)
def capture_command(
    target_date: datetime | None, config_path: Path, alert_name: str | None
) -> None:
    """Capture Open-Meteo responses and save as replayable test fixtures."""
    app_config = load_app_config(config_path)
    capture_date = target_date.date() if target_date else date.today()
    is_historical = capture_date < date.today()

    if alert_name:
        profile = next((a for a in app_config.alerts if a.name == alert_name), None)
        if profile is None:
            raise click.ClickException(f"Unknown alert profile: {alert_name!r}")
        profiles = [profile]
    else:
        profiles = list(app_config.alerts)

    for profile in profiles:
        click.echo(f"Capturing {profile.name} for {capture_date}...")
        _capture_profile(profile, capture_date, is_historical)

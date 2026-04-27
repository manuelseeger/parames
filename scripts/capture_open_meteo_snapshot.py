from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import click

from parames.config import load_app_config
from parames.evaluation import evaluate
from parames.forecast import LEGACY_MODEL_ALIASES, OpenMeteoForecastClient, ZURICH_TIMEZONE


def _build_requests(profile) -> list[dict[str, object]]:
    hourly_variables = [
        f"wind_speed_{profile.wind_level_m}m",
        f"wind_direction_{profile.wind_level_m}m",
        "precipitation",
        "pressure_msl",
    ]
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
        if profile.bise and profile.bise.enabled:
            requests.append(
                {
                    "name": f"west_{model}",
                    "location": profile.bise.pressure_reference_west.model_dump(),
                    "model": model,
                    "hourly_variables": ["pressure_msl"],
                }
            )
            requests.append(
                {
                    "name": f"east_{model}",
                    "location": profile.bise.pressure_reference_east.model_dump(),
                    "model": model,
                    "hourly_variables": ["pressure_msl"],
                }
            )
    return requests


def _capture_response_payload(
    client: OpenMeteoForecastClient,
    request: dict[str, object],
) -> dict[str, object]:
    location = request["location"]
    model = str(request["model"])
    hourly_variables = request["hourly_variables"]
    response = client._client.get(
        "",
        params={
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "hourly": ",".join(hourly_variables),
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
    return payload


@click.command()
@click.argument("snapshot_name")
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
    default="zurich_bise",
    show_default=True,
    help="Configured alert profile name to capture.",
)
def main(snapshot_name: str, config_path: Path, alert_name: str) -> None:
    """Capture live Open-Meteo responses and save them as replayable test fixtures."""
    app_config = load_app_config(config_path)
    profile = next((alert for alert in app_config.alerts if alert.name == alert_name), None)
    if profile is None:
        raise click.ClickException(f"Unknown alert profile: {alert_name}")

    fixture_dir = Path("tests/fixtures/open_meteo") / snapshot_name
    fixture_dir.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now(ZoneInfo(ZURICH_TIMEZONE)).replace(microsecond=0)
    requests = _build_requests(profile)

    with OpenMeteoForecastClient() as client:
        for request in requests:
            payload = _capture_response_payload(client, request)
            (fixture_dir / f"{request['name']}.json").write_text(
                json.dumps(payload, indent=2),
                encoding="utf-8",
            )
        windows = evaluate(profile, client=client, now=captured_at)

    metadata = {
        "captured_at": captured_at.isoformat(),
        "timezone": ZURICH_TIMEZONE,
        "profile_name": profile.name,
        "requests": requests,
        "expected_windows": [window.model_dump(mode="json") for window in windows],
    }
    (fixture_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    click.echo(f"Saved snapshot to {fixture_dir}")
    click.echo(json.dumps(metadata["expected_windows"], indent=2))


if __name__ == "__main__":
    main()

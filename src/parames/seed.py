"""Seed alert definitions from a YAML config file into MongoDB.

Usage: parames seed --config config/default.yaml

Idempotent — upserts by name, so safe to run repeatedly.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import click

from parames.config import RuntimeSettings, load_app_config
from parames.persistence import AlertRepository, build_engine
from parames.persistence.models import AlertDefinition


def _profile_to_definition(profile) -> AlertDefinition:
    return AlertDefinition(
        name=profile.name,
        description=profile.description,
        enabled=True,
        location=profile.location,
        models=profile.models,
        forecast_hours=profile.forecast_hours,
        wind_level_m=profile.wind_level_m,
        model_agreement=profile.model_agreement,
        wind=profile.wind,
        time_window=profile.time_window,
        dry=profile.dry,
        plugins=profile.plugins,
        delivery=profile.delivery,
        suppress_duplicates=profile.suppress_duplicates,
    )


async def _seed(config_path: Path) -> None:
    app_config = load_app_config(config_path)
    settings = RuntimeSettings()
    engine = build_engine(settings.mongo_uri)
    repo = AlertRepository(engine)

    for profile in app_config.alerts:
        definition = _profile_to_definition(profile)
        result = await repo.upsert_alert_definition(definition)
        click.echo(f"  Upserted: {result.name} (id={result.id})")


@click.command("seed")
@click.option(
    "--config",
    "config_path",
    default=lambda: str(RuntimeSettings().config_path),
    show_default=True,
    type=click.Path(exists=True, path_type=Path, dir_okay=False),
    help="Path to the YAML config file to seed from.",
)
def seed_command(config_path: Path) -> None:
    """Seed alert definitions from YAML into MongoDB (idempotent)."""
    click.echo(f"Seeding from {config_path} …")
    asyncio.run(_seed(config_path))
    click.echo("Done.")

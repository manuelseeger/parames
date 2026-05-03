from __future__ import annotations

import asyncio
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import click

from parames.capture import _ReplayClient, _build_requests, _fetch_historical_payloads
from parames.config import RuntimeSettings, load_app_config
from parames.delivery.delivery_cli import ConsoleChannel
from parames.domain import CandidateWindow
from parames.evaluation import evaluate
from parames.forecast import OpenMeteoForecastClient, ZURICH_TIMEZONE
from parames.persistence import AlertRepository, build_engine


async def _persist_windows(
    *,
    repo: AlertRepository,
    profile_name: str,
    windows: list[CandidateWindow],
    alert_definition_id,
    run_id,
) -> None:
    for window in windows:
        existing = await repo.find_matching_detection(profile_name, window, is_backtest=True)
        await repo.upsert_detection(
            window,
            alert_definition_id=alert_definition_id,
            run_id=run_id,
            existing=existing,
            is_backtest=True,
        )


async def _run_backtest(
    *,
    profiles,
    now: datetime,
    capture_date: date,
    scoring,
    persist: bool,
    config_path: Path,
) -> None:
    channel = ConsoleChannel()
    repo: AlertRepository | None = None
    run_doc = None
    total_windows = 0

    if persist:
        settings = RuntimeSettings()
        engine = build_engine(settings.mongo_uri)
        repo = AlertRepository(engine)

    for profile in profiles:
        click.echo(f"Fetching historical forecast for {profile.name} on {capture_date}…")
        requests = _build_requests(profile)
        payloads = _fetch_historical_payloads(requests, capture_date)

        with OpenMeteoForecastClient() as normalizer:
            replay_client = _ReplayClient(payloads, requests, normalizer)
            windows = evaluate(profile, client=replay_client, now=now, scoring=scoring)

        total_windows += len(windows)
        await channel.deliver(profile.name, windows)

        if persist and repo is not None and windows:
            definition = await repo.get_alert_definition_by_name(profile.name)
            if definition is None:
                click.echo(
                    f"  ⚠ No DB definition for {profile.name!r} — skipping persistence. "
                    "Run 'parames seed' first.",
                    err=True,
                )
                continue

            if run_doc is None:
                run_doc = await repo.start_run(
                    config_path=str(config_path),
                    alert_definition_ids=[definition.id],
                    is_backtest=True,
                )
            elif definition.id not in run_doc.alert_definition_ids:
                run_doc.alert_definition_ids.append(definition.id)

            await _persist_windows(
                repo=repo,
                profile_name=profile.name,
                windows=windows,
                alert_definition_id=definition.id,
                run_id=run_doc.id,
            )
            click.echo(f"  Saved {len(windows)} detection(s) to database.")

    if persist and repo is not None and run_doc is not None:
        await repo.finish_run(
            run_doc,
            status="completed",
            windows_found=total_windows,
            deliveries_attempted=0,
            deliveries_suppressed=0,
        )


@click.command("backtest")
@click.option(
    "--date",
    "target_date",
    required=True,
    metavar="YYYY-MM-DD",
    help="Past date to evaluate (must be before today).",
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
    help="Alert profile name to backtest. Runs all configured alerts if omitted.",
)
@click.option(
    "--persist",
    is_flag=True,
    default=False,
    help="Save results to MongoDB so they appear in the web UI.",
)
def backtest_command(
    target_date: datetime, config_path: Path, alert_name: str | None, persist: bool
) -> None:
    """Run evaluation on a historical date without sending alerts.

    Use --persist to save results to the database for review in the web UI.
    """
    capture_date = target_date.date()
    if capture_date >= date.today():
        raise click.ClickException("--date must be a past date (before today).")

    app_config = load_app_config(config_path)

    if alert_name:
        profile = next((a for a in app_config.alerts if a.name == alert_name), None)
        if profile is None:
            raise click.ClickException(f"Unknown alert profile: {alert_name!r}")
        profiles = [profile]
    else:
        profiles = list(app_config.alerts)

    # Simulate evaluation as of noon on the target date so the full-day window is in range.
    now = datetime(
        capture_date.year, capture_date.month, capture_date.day, 12, 0,
        tzinfo=ZoneInfo(ZURICH_TIMEZONE),
    )

    asyncio.run(
        _run_backtest(
            profiles=profiles,
            now=now,
            capture_date=capture_date,
            scoring=app_config.scoring,
            persist=persist,
            config_path=config_path,
        )
    )

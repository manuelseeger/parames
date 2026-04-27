from __future__ import annotations

import asyncio
from pathlib import Path

import click

from parames.config import AppConfig, RuntimeSettings, load_app_config
from parames.delivery.delivery_cli import ConsoleChannel, DeliveryChannel
from parames.delivery.delivery_telegram import TelegramChannel
from parames.domain import CandidateWindow
from parames.evaluation import evaluate
from parames.forecast import ForecastClientError, OpenMeteoForecastClient
from parames.persistence import AlertRepository, build_engine


def _default_config_path() -> Path:
    return RuntimeSettings().config_path


def _build_channels(app_config: AppConfig, settings: RuntimeSettings) -> dict[str, DeliveryChannel]:
    channels: dict[str, DeliveryChannel] = {}
    for name, cfg in app_config.delivery_channels.items():
        if cfg.type == "console":
            channels[name] = ConsoleChannel()
        elif cfg.type == "telegram":
            if settings.telegram_bot_token is None:
                raise click.ClickException(
                    f"delivery_channels.{name}: PARAMES_TELEGRAM_BOT_TOKEN is not set"
                )
            chat_id = cfg.model_extra.get("chat_id")
            if not chat_id:
                raise click.ClickException(f"delivery_channels.{name}: 'chat_id' is required")
            channels[name] = TelegramChannel(
                bot_token=settings.telegram_bot_token.get_secret_value(),
                chat_id=chat_id,
            )
        else:
            raise click.ClickException(f"Unsupported delivery channel type: {cfg.type!r}")
    return channels


async def _deliver_window(
    *,
    profile_name: str,
    window: CandidateWindow,
    alert_doc,
    channel_names: list[str],
    channels: dict[str, DeliveryChannel],
    channel_types: dict[str, str],
    repo: AlertRepository,
    run_id,
) -> tuple[int, int]:
    """Returns (attempted, suppressed) counts for one window."""
    attempted = 0
    suppressed = 0
    for channel_name in channel_names:
        channel = channels.get(channel_name)
        if channel is None:
            raise click.ClickException(f"Unsupported delivery channel: {channel_name!r}")
        if not channel.dedupe:
            # Channels like console always fire and aren't recorded — they're transient output.
            await channel.deliver(profile_name, [window])
            continue
        if await repo.was_delivered(alert_doc.id, channel_name):
            suppressed += 1
            continue
        attempted += 1
        try:
            await channel.deliver(profile_name, [window])
        except Exception as exc:  # noqa: BLE001 — record any channel-side failure
            await repo.record_delivery(
                alert_id=alert_doc.id,
                run_id=run_id,
                channel_name=channel_name,
                channel_type=channel_types[channel_name],
                status="failed",
                error=str(exc),
            )
            continue
        await repo.record_delivery(
            alert_id=alert_doc.id,
            run_id=run_id,
            channel_name=channel_name,
            channel_type=channel_types[channel_name],
            status="sent",
        )
    return attempted, suppressed


async def _run(config_path: Path) -> None:
    settings = RuntimeSettings()
    app_config = load_app_config(config_path)
    channels = _build_channels(app_config, settings)
    channel_types = {name: cfg.type for name, cfg in app_config.delivery_channels.items()}

    engine = build_engine(settings.mongo_uri)
    repo = AlertRepository(engine)
    run = await repo.start_run(
        config_path=str(config_path),
        alert_names=[alert.name for alert in app_config.alerts],
    )

    windows_found = 0
    deliveries_attempted = 0
    deliveries_suppressed = 0
    status: str = "completed"
    error: str | None = None
    try:
        with OpenMeteoForecastClient() as client:
            for profile in app_config.alerts:
                profile_windows = evaluate(profile, client=client)
                windows_found += len(profile_windows)
                for window in profile_windows:
                    existing = await repo.find_matching_alert(profile.name, window)
                    alert_doc = await repo.upsert_alert(window, run_id=run.id, existing=existing)
                    attempted, suppressed = await _deliver_window(
                        profile_name=profile.name,
                        window=window,
                        alert_doc=alert_doc,
                        channel_names=profile.delivery,
                        channels=channels,
                        channel_types=channel_types,
                        repo=repo,
                        run_id=run.id,
                    )
                    deliveries_attempted += attempted
                    deliveries_suppressed += suppressed
    except Exception as exc:  # noqa: BLE001 — record any failure on the run doc
        status = "failed"
        error = str(exc)
        raise
    finally:
        await repo.finish_run(
            run,
            status=status,  # type: ignore[arg-type]
            error=error,
            windows_found=windows_found,
            deliveries_attempted=deliveries_attempted,
            deliveries_suppressed=deliveries_suppressed,
        )


@click.command()
@click.option(
    "--config",
    "config_path",
    default=lambda: str(_default_config_path()),
    show_default=True,
    type=click.Path(exists=True, path_type=Path, dir_okay=False),
    help="Path to the YAML configuration file.",
)
def main(config_path: Path) -> None:
    """Evaluate configured wind alerts and print candidates."""
    try:
        asyncio.run(_run(config_path))
    except (OSError, ValueError, ForecastClientError) as exc:
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":
    main()

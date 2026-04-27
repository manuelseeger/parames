from __future__ import annotations

import asyncio
from pathlib import Path

import click

from parames.config import AppConfig, RuntimeSettings, load_app_config
from parames.delivery.delivery_cli import ConsoleChannel, DeliveryChannel
from parames.delivery.delivery_telegram import TelegramChannel
from parames.evaluation import evaluate
from parames.forecast import ForecastClientError, OpenMeteoForecastClient


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


async def _run(config_path: Path) -> None:
    settings = RuntimeSettings()
    app_config = load_app_config(config_path)
    channels = _build_channels(app_config, settings)
    with OpenMeteoForecastClient() as client:
        for alert in app_config.alerts:
            windows = evaluate(alert, client=client)
            for channel_name in alert.delivery:
                channel = channels.get(channel_name)
                if channel is None:
                    raise click.ClickException(f"Unsupported delivery channel: {channel_name!r}")
                await channel.deliver(alert.name, windows)


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

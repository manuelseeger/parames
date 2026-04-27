from __future__ import annotations

from pathlib import Path

import click

from parames.config import RuntimeSettings, load_app_config
from parames.delivery import ConsoleChannel
from parames.evaluation import evaluate
from parames.forecast import ForecastClientError, OpenMeteoForecastClient


def _default_config_path() -> Path:
    return RuntimeSettings().config_path


@click.command()
@click.option(
    "--config",
    "config_path",
    default=lambda: str(_default_config_path()),
    show_default=True,
    type=click.Path(path_type=Path, dir_okay=False),
    help="Path to the YAML configuration file.",
)
def main(config_path: Path) -> None:
    """Evaluate configured wind alerts and print candidates."""
    try:
        app_config = load_app_config(config_path)
        with OpenMeteoForecastClient() as client:
            channels = {"console": ConsoleChannel()}
            for alert in app_config.alerts:
                windows = evaluate(alert, client=client)
                for channel_name in alert.delivery:
                    channel = channels.get(channel_name)
                    if channel is None:
                        raise click.ClickException(
                            f"Unsupported delivery channel: {channel_name}"
                        )
                    channel.deliver(alert.name, windows)
    except (OSError, ValueError, ForecastClientError) as exc:
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":
    main()

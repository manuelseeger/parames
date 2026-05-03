from __future__ import annotations

import asyncio
from pathlib import Path

import click

from parames.backtest import backtest_command
from parames.capture import capture_command
from parames.forecast import ForecastClientError
from parames.runner import default_config_path, run
from parames.seed import seed_command


@click.group()
def main() -> None:
    """Parames — paragliding wind alert tool."""


@main.command("run")
@click.option(
    "--config",
    "config_path",
    default=lambda: str(default_config_path()),
    show_default=True,
    type=click.Path(exists=True, path_type=Path, dir_okay=False),
    help="Path to the YAML configuration file.",
)
def run_command(config_path: Path) -> None:
    """Evaluate configured wind alerts and deliver candidates."""
    try:
        asyncio.run(run(config_path))
    except (OSError, ValueError, ForecastClientError) as exc:
        raise click.ClickException(str(exc)) from exc


main.add_command(seed_command)
main.add_command(capture_command)
main.add_command(backtest_command)


if __name__ == "__main__":
    main()

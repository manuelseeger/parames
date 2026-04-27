from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from rich.console import Console
from rich.rule import Rule

from parames.domain import CandidateWindow


class DeliveryChannel(Protocol):
    def deliver(self, alert_name: str, windows: Sequence[CandidateWindow]) -> None:
        ...


class ConsoleChannel:
    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()

    def deliver(self, alert_name: str, windows: Sequence[CandidateWindow]) -> None:
        if not windows:
            self._console.print(f"No candidate NE/E wind windows found for {alert_name} in the forecast horizon.")
            return

        self._console.print(Rule(f"Wind Alert Candidates - {alert_name}"))
        for window in windows:
            classification = window.classification.upper()
            self._console.print(classification, style="bold green" if window.score >= 5 else "bold yellow")
            self._console.print(
                f"{window.start:%a %Y-%m-%d %H:%M}-{window.end:%H:%M} | "
                f"Duration: {window.duration_hours}h | Score: {window.score}/7"
            )
            self._console.print(
                f"Wind: avg {window.avg_wind_speed_kmh:.1f} km/h, "
                f"max {window.max_wind_speed_kmh:.1f} km/h"
            )
            self._console.print(f"Direction: avg {window.avg_direction_deg:.0f} deg")
            if window.bise_pressure_gradient_hpa is None:
                self._console.print("Bise pressure gradient: unavailable")
            else:
                self._console.print(
                    f"Bise pressure gradient: +{window.bise_pressure_gradient_hpa:.1f} hPa east-west"
                )
            self._console.print(
                f"Dry filter: {'enabled' if window.dry_filter_applied else 'disabled'}"
            )
            self._console.print()

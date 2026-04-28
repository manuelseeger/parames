from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from rich.console import Console
from rich.rule import Rule
from rich.text import Text

from parames.delivery._charts import COL_W, compass, vbar
from parames.domain import CandidateWindow, WindowHour


def _render_horizontal_charts(console: Console, hours: list[WindowHour]) -> None:
    if not hours:
        return

    max_speed = max(h.avg_wind_speed_kmh for h in hours)

    def speed_style(h: WindowHour) -> str:
        if not h.in_window:
            return "dim"
        return "bold green" if h.avg_wind_speed_kmh >= 40 else "bold yellow"

    time_row  = Text("  ")
    bar_row   = Text("  ")
    speed_row = Text("  ")
    arrow_row = Text("  ")
    label_row = Text("  ")
    precip_row = Text("  ")

    for h in hours:
        col = COL_W
        sty = speed_style(h)
        time_sty = "bold" if h.in_window else "dim"
        dir_sty  = "bold cyan" if h.in_window else "dim"

        arrow, label = compass(h.avg_direction_deg)
        time_row.append(f"{h.time:%H:%M}".ljust(col), style=time_sty)
        bar_row.append(vbar(h.avg_wind_speed_kmh, max_speed).ljust(col), style=sty)
        speed_row.append(f"{h.avg_wind_speed_kmh:.0f}".ljust(col), style=sty)
        arrow_row.append(arrow.ljust(col), style=sty)
        label_row.append(label.ljust(col), style=dir_sty)
        precipitation = "-" if h.avg_precipitation_mm_per_hour is None else f"{h.avg_precipitation_mm_per_hour:.1f}"
        precip_row.append(precipitation.ljust(col), style=("bold blue" if h.in_window else "dim"))

    console.print("  [bold]💨 Speed  🧭 Direction  💧 Precip (mm/h)[/bold]")
    console.print(time_row)
    console.print(bar_row)
    console.print(speed_row)
    console.print(arrow_row)
    console.print(label_row)
    console.print(precip_row)


class DeliveryChannel(Protocol):
    async def deliver(self, alert_name: str, windows: Sequence[CandidateWindow]) -> None:
        ...


class ConsoleChannel:
    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()

    async def deliver(self, alert_name: str, windows: Sequence[CandidateWindow]) -> None:
        if not windows:
            self._console.print(f"🌬️  No candidate NE/E wind windows found for [bold]{alert_name}[/bold] in the forecast horizon.")
            return

        self._console.print(Rule(f"🪂 Wind Alert Candidates — {alert_name}"))
        for window in windows:
            classification = window.classification.upper()
            score = window.score
            score_style = "bold green" if score >= 5 else "bold yellow"
            medal = "🟢" if score >= 5 else "🟡"
            self._console.print(f"{medal} [bold]{classification}[/bold]", style=score_style)
            self._console.print(
                f"  📅 {window.start:%a %Y-%m-%d %H:%M} – {window.end:%H:%M}  "
                f"⏱ {window.duration_hours}h  "
                f"⭐ Score: {score}/7"
            )
            self._console.print(
                f"  💨 avg {window.avg_wind_speed_kmh:.1f} km/h, "
                f"max {window.max_wind_speed_kmh:.1f} km/h"
            )
            self._console.print(f"  🧭 Direction: avg {window.avg_direction_deg:.0f}°")
            bise = window.plugin_outputs.get("bise", {}).get("gradient_hpa")
            if bise is None:
                self._console.print("  🌡  Bise gradient: unavailable")
            else:
                self._console.print(f"  🌡  Bise gradient: +{bise:.1f} hPa east-west")
            self._console.print(
                "  💧 Precipitation: "
                + (
                    "unavailable"
                    if window.avg_precipitation_mm_per_hour is None
                    else f"avg {window.avg_precipitation_mm_per_hour:.1f} mm/h, max {window.max_precipitation_mm_per_hour:.1f} mm/h"
                )
            )
            if window.hours:
                self._console.print()
                _render_horizontal_charts(self._console, window.hours)
            self._console.print()

from __future__ import annotations

import re
from collections.abc import Sequence

from aiogram import Bot
from aiogram.enums import ParseMode


from parames.delivery._charts import COL_W, compass, vbar
from parames.domain import CandidateWindow, WindowHour

# Characters that must be escaped in MarkdownV2 (outside code blocks).
_MD2_RE = re.compile(r'([-_*\[\]()~`>#+=|{}.!\\])')


def _md2(text: str) -> str:
    return _MD2_RE.sub(r'\\\1', text)


def _build_chart(hours: list[WindowHour]) -> str:
    if not hours:
        return ""

    max_speed = max(h.avg_wind_speed_kmh for h in hours)

    rows: list[list[str]] = [[], [], [], [], [], []]
    for h in hours:
        arrow, label = compass(h.avg_direction_deg)
        precip = "-" if h.avg_precipitation_mm_per_hour is None else f"{h.avg_precipitation_mm_per_hour:.1f}"
        rows[0].append(f"{h.time:%H:%M}".ljust(COL_W))
        rows[1].append(vbar(h.avg_wind_speed_kmh, max_speed).ljust(COL_W))
        rows[2].append(f"{h.avg_wind_speed_kmh:.0f}".ljust(COL_W))
        rows[3].append(arrow.ljust(COL_W))
        rows[4].append(label.ljust(COL_W))
        rows[5].append(precip.ljust(COL_W))

    header = "Speed (km/h)  Direction  Precip (mm/h)"
    lines = [header] + ["  " + "".join(row) for row in rows]
    return "\n".join(lines)


def _format_window(alert_name: str, window: CandidateWindow) -> str:
    if window.score is None:
        medal = "⚪"
        score_str = "unavailable"
    elif window.score >= 85:
        medal = "🌟"
        score_str = str(window.score)
    elif window.score >= 70:
        medal = "🟢"
        score_str = str(window.score)
    else:
        medal = "🟡"
        score_str = str(window.score)
    classification = window.classification.upper()

    header = (
        f"{medal} *{_md2(alert_name)} — {_md2(classification)}*  ⭐ {_md2(score_str)}"
    )
    date_line = (
        f"📅 {_md2(window.start.strftime('%a %Y-%m-%d %H:%M'))} – "
        f"{_md2(window.end.strftime('%H:%M'))}  "
        f"⏱ {window.duration_hours}h"
    )
    wind_line = (
        f"💨 avg {_md2(f'{window.avg_wind_speed_kmh:.1f}')} km/h, "
        f"max {_md2(f'{window.max_wind_speed_kmh:.1f}')} km/h"
    )
    dir_line = f"🧭 avg {_md2(f'{window.avg_direction_deg:.0f}')}°"

    bise_gradient = window.plugin_outputs.get("bise", {}).get("gradient_hpa")
    if bise_gradient is None:
        bise_line = "🌡 Bise gradient: unavailable"
    else:
        bise_line = f"🌡 Bise gradient: \\+{_md2(f'{bise_gradient:.1f}')} hPa east\\-west"

    if window.avg_precipitation_mm_per_hour is None:
        precip_line = "💧 Precipitation: unavailable"
    else:
        precip_line = (
            f"💧 Precipitation: avg {_md2(f'{window.avg_precipitation_mm_per_hour:.1f}')} mm/h, "
            f"max {_md2(f'{window.max_precipitation_mm_per_hour:.1f}')} mm/h"
        )

    parts = [header, date_line, wind_line, dir_line, bise_line, precip_line]

    chart = _build_chart(window.hours)
    if chart:
        parts.append(f"```\n{chart}\n```")

    return "\n".join(parts)


class TelegramChannel:
    def __init__(self, *, bot_token: str, chat_id: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id

    async def deliver(self, alert_name: str, windows: Sequence[CandidateWindow]) -> None:
        if not windows:
            return

        async with Bot(token=self._bot_token) as bot:
            for window in windows:
                text = _format_window(alert_name, window)
                await bot.send_message(
                    chat_id=self._chat_id,
                    text=text,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )

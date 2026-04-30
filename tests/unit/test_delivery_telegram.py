from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from parames.delivery.delivery_telegram import TelegramChannel, _format_window, _md2
from parames.domain import CandidateWindow, WindowHour


def _make_window(
    *,
    score: int | None = 50,
    classification: str = "candidate",
    avg_precipitation_mm_per_hour: float | None = 0.4,
    bise_gradient_hpa: float | None = 2.0,
    hours: list[WindowHour] | None = None,
) -> CandidateWindow:
    return CandidateWindow(
        alert_name="zurich_bise",
        start=datetime(2026, 4, 29, 11, 0),
        end=datetime(2026, 4, 29, 13, 0),
        duration_hours=2,
        avg_wind_speed_kmh=10.5,
        max_wind_speed_kmh=12.0,
        avg_direction_deg=60.0,
        avg_precipitation_mm_per_hour=avg_precipitation_mm_per_hour,
        max_precipitation_mm_per_hour=0.7,
        models=["icon_d2", "meteoswiss_icon_ch2"],
        dry_filter_applied=False,
        score=score,
        classification=classification,
        hours=hours or [],
        plugin_outputs={"bise": {"gradient_hpa": bise_gradient_hpa}} if bise_gradient_hpa is not None else {},
    )


# --- Pure unit tests (no network) ---

def test_md2_escapes_all_special_chars() -> None:
    special = r"_*[]()~`>#+=|{}.!-"
    escaped = _md2(special)
    for ch in special:
        assert f"\\{ch}" in escaped, f"char {ch!r} not escaped"


def test_md2_leaves_plain_text_unchanged() -> None:
    assert _md2("Hello world 123") == "Hello world 123"


def test_format_window_contains_alert_name() -> None:
    text = _format_window("zurich_bise", _make_window())
    assert "zurich" in text


def test_format_window_contains_score() -> None:
    text = _format_window("alert", _make_window(score=78))
    assert "78" in text


def test_format_window_unavailable_score_renders_marker() -> None:
    text = _format_window("alert", _make_window(score=None, classification="unavailable"))
    assert "unavailable" in text


def test_format_window_contains_precipitation() -> None:
    text = _format_window("alert", _make_window(avg_precipitation_mm_per_hour=0.4))
    assert "0" in text and "4" in text


def test_format_window_unavailable_precipitation() -> None:
    text = _format_window("alert", _make_window(avg_precipitation_mm_per_hour=None))
    assert "unavailable" in text


def test_format_window_unavailable_bise() -> None:
    text = _format_window("alert", _make_window(bise_gradient_hpa=None))
    assert "unavailable" in text


def test_format_window_includes_chart_block() -> None:
    window = _make_window(
        hours=[
            WindowHour(time=datetime(2026, 4, 29, 11, 0), avg_wind_speed_kmh=10.0, avg_direction_deg=60.0),
            WindowHour(time=datetime(2026, 4, 29, 12, 0), avg_wind_speed_kmh=14.0, avg_direction_deg=70.0),
        ]
    )
    text = _format_window("alert", window)
    assert "```" in text
    assert "11:00" in text


# --- Async behaviour tests ---

def test_empty_windows_sends_nothing() -> None:
    channel = TelegramChannel(bot_token="fake", chat_id="@test")
    mock_bot = AsyncMock()
    mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)

    with patch("parames.delivery.delivery_telegram.Bot", return_value=mock_bot):
        asyncio.run(channel.deliver("alert", []))

    mock_bot.send_message.assert_not_called()


def test_one_window_sends_one_message() -> None:
    channel = TelegramChannel(bot_token="fake", chat_id="@test_channel")
    mock_bot = AsyncMock()
    mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)

    with patch("parames.delivery.delivery_telegram.Bot", return_value=mock_bot):
        asyncio.run(channel.deliver("zurich_bise", [_make_window()]))

    mock_bot.send_message.assert_called_once()
    kwargs = mock_bot.send_message.call_args.kwargs
    assert kwargs["chat_id"] == "@test_channel"
    assert kwargs["parse_mode"].value == "MarkdownV2"
    assert "zurich" in kwargs["text"]


def test_two_windows_send_two_messages() -> None:
    channel = TelegramChannel(bot_token="fake", chat_id="@test_channel")
    mock_bot = AsyncMock()
    mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)

    with patch("parames.delivery.delivery_telegram.Bot", return_value=mock_bot):
        asyncio.run(channel.deliver("alert", [_make_window(score=50), _make_window(score=80)]))

    assert mock_bot.send_message.call_count == 2

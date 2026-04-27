from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from parames.config import AppConfig, load_app_config


@pytest.fixture
def zurich_tz() -> ZoneInfo:
    return ZoneInfo("Europe/Zurich")


@pytest.fixture
def default_config() -> AppConfig:
    return load_app_config(__import__("pathlib").Path("config/default.yaml"))


@pytest.fixture
def fixed_now(zurich_tz: ZoneInfo) -> datetime:
    return datetime(2026, 4, 27, 10, 0, tzinfo=zurich_tz)

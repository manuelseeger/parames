from __future__ import annotations

import asyncio
from importlib.metadata import version
from types import SimpleNamespace

from parames.api.routers.health import healthz


def test_healthz_includes_running_app_version() -> None:
    request = SimpleNamespace(app=SimpleNamespace(version="0.1.4"))

    assert asyncio.run(healthz(request)) == {"status": "ok", "version": "0.1.4"}


def test_api_app_version_matches_project_version() -> None:
    from parames.api.main import app

    assert app.version == version("parames")

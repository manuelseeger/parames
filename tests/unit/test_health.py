from __future__ import annotations

import asyncio
from types import SimpleNamespace

from parames.api.routers.health import healthz


def test_healthz_includes_running_app_version() -> None:
    request = SimpleNamespace(app=SimpleNamespace(version="0.1.3"))

    assert asyncio.run(healthz(request)) == {"status": "ok", "version": "0.1.3"}

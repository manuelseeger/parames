from __future__ import annotations

import asyncio
import logging

from bson import ObjectId

from parames.logging import LogRecorder, run_log_context


class _LogRepo:
    def __init__(self) -> None:
        self.entries = []

    async def record_log(self, entry) -> None:
        self.entries.append(entry)


def test_persists_exception_with_its_run_id() -> None:
    async def scenario() -> None:
        repo = _LogRepo()
        recorder = LogRecorder(repo, "scheduler")
        recorder.install()
        run_id = ObjectId()
        logger = logging.getLogger("parames.runner")
        try:
            with run_log_context(run_id):
                try:
                    raise RuntimeError("Open-Meteo overloaded")
                except RuntimeError:
                    logger.exception("Alert run failed")
            await asyncio.sleep(0)
        finally:
            recorder.close()

        assert len(repo.entries) == 1
        entry = repo.entries[0]
        assert entry.level == "ERROR"
        assert str(entry.run_id) == str(run_id)
        assert "RuntimeError: Open-Meteo overloaded" in entry.text

    asyncio.run(scenario())

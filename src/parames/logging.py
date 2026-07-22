from __future__ import annotations

import asyncio
import contextvars
import logging
import re
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Literal

from bson import BSON

from parames.config import RuntimeSettings
from parames.persistence.models import LogEntry

run_id_context: contextvars.ContextVar[object | None] = contextvars.ContextVar("log_run_id", default=None)

# Keep this intentionally broad: this application is unauthenticated.
_SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)\S+"),
    re.compile(r"(?i)\b(token|password|api[_-]?key|secret)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(mongodb(?:\+srv)?://[^:/\s]+:)([^@\s]+)(@)"),
]


def redact(text: str) -> str:
    settings = RuntimeSettings()
    secrets = [settings.mongo_uri]
    if settings.telegram_bot_token:
        secrets.append(settings.telegram_bot_token.get_secret_value())
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = _SECRET_PATTERNS[0].sub(r"\1[REDACTED]", text)
    text = _SECRET_PATTERNS[1].sub(lambda m: f"{m.group(1)}=[REDACTED]", text)
    return _SECRET_PATTERNS[2].sub(r"\1[REDACTED]\3", text)


@contextmanager
def run_log_context(run_id: object):
    token = run_id_context.set(run_id)
    try:
        yield
    finally:
        run_id_context.reset(token)


class _PersistingHandler(logging.Handler):
    def __init__(self, recorder: "LogRecorder") -> None:
        super().__init__(level=logging.INFO)
        self.recorder = recorder

    def emit(self, record: logging.LogRecord) -> None:
        # INFO is retained only for us; warnings/errors from all loggers are useful.
        if record.levelno < logging.WARNING and not record.name.startswith("parames"):
            return
        try:
            self.recorder.record(
                level=record.levelname,
                text=self.format(record),
                logger_name=record.name,
                source="logging",
                occurred_at=datetime.fromtimestamp(record.created, timezone.utc),
            )
        except Exception:
            self.handleError(record)


class _CapturedStream:
    def __init__(self, recorder: "LogRecorder", original, level: str) -> None:
        self.recorder, self.original, self.level, self.buffer = recorder, original, level, ""

    def write(self, text: str) -> int:
        self.original.write(text)
        self.buffer += text
        lines = self.buffer.splitlines(keepends=True)
        self.buffer = ""
        for line in lines:
            if line.endswith(("\n", "\r")):
                value = line.rstrip("\r\n")
                if value:
                    self.recorder.record(level=self.level, text=value, source="stream")
            else:
                self.buffer = line
        return len(text)

    def flush(self) -> None:
        self.original.flush()

    def flush_partial(self) -> None:
        if self.buffer:
            self.recorder.record(level=self.level, text=self.buffer, source="stream")
            self.buffer = ""

    def __getattr__(self, name):
        return getattr(self.original, name)


class LogRecorder:
    """Best-effort process-local sink. Persistence failures never escape callers."""
    def __init__(self, repo, service: Literal["api", "scheduler"]) -> None:
        self.repo, self.service = repo, service
        self._stdout = self._stderr = None

    def record(self, *, level: str, text: str, source: str, logger_name: str | None = None,
               occurred_at: datetime | None = None) -> None:
        text = redact(text)
        entry = LogEntry(
            occurred_at=occurred_at or datetime.now(timezone.utc), service=self.service,
            level=level, logger_name=logger_name, source=source, text=text,
            run_id=run_id_context.get(),
        )
        # Mongo rejects documents over 16 MiB. Drop rather than alter evidence.
        try:
            if len(BSON.encode(entry.model_dump(by_alias=True, exclude={"id"}))) > 16 * 1024 * 1024:
                return
            loop = asyncio.get_running_loop()
            loop.create_task(self._save(entry))
        except Exception:
            return

    async def _save(self, entry: LogEntry) -> None:
        try:
            await self.repo.record_log(entry)
        except Exception:
            pass

    def install(self) -> None:
        handler = _PersistingHandler(self)
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
        logging.getLogger().addHandler(handler)
        self._stdout = _CapturedStream(self, sys.stdout, "INFO")
        self._stderr = _CapturedStream(self, sys.stderr, "ERROR")
        sys.stdout, sys.stderr = self._stdout, self._stderr

    def close(self) -> None:
        if self._stdout:
            self._stdout.flush_partial()
            sys.stdout = self._stdout.original
        if self._stderr:
            self._stderr.flush_partial()
            sys.stderr = self._stderr.original

from __future__ import annotations

import base64
from datetime import datetime
from typing import Literal

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from parames.api.deps import Repo
from parames.persistence.models import LogEntry

router = APIRouter(prefix="/logs", tags=["logs"])
LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class LogPage(BaseModel):
    entries: list[LogEntry]
    next_cursor: str | None = None


def _decode_cursor(value: str) -> tuple[datetime, str]:
    try:
        timestamp, entry_id = base64.urlsafe_b64decode(value.encode()).decode().split("|", 1)
        return datetime.fromisoformat(timestamp), entry_id
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Invalid log cursor") from exc


def _cursor(entry: LogEntry) -> str:
    return base64.urlsafe_b64encode(f"{entry.occurred_at.isoformat()}|{entry.id}".encode()).decode()


@router.get("", response_model=LogPage)
async def list_logs(
    repo: Repo,
    limit: int = Query(default=200, ge=1, le=200),
    service: Literal["api", "scheduler"] | None = None,
    min_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = None,
    search: str | None = Query(default=None, max_length=500),
    run_id: str | None = None,
    cursor: str | None = None,
) -> LogPage:
    if run_id and not ObjectId.is_valid(run_id):
        raise HTTPException(status_code=422, detail="Invalid run_id")
    entries = await repo.list_logs(
        limit=limit, service=service, min_level=min_level, search=search,
        run_id=run_id, cursor=_decode_cursor(cursor) if cursor else None,
    )
    return LogPage(entries=entries, next_cursor=_cursor(entries[-1]) if len(entries) == limit else None)

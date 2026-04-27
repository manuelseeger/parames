from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Literal

from pyodmongo import DbModel, Field, Id
from pymongo import ASCENDING, DESCENDING, IndexModel

from parames.domain import CandidateWindow

RunStatus = Literal["running", "completed", "failed"]
DeliveryStatus = Literal["sent", "failed", "skipped"]


class RunDoc(DbModel):
    started_at: datetime
    finished_at: datetime | None = None
    status: RunStatus = "running"
    error: str | None = None
    config_path: str
    alert_names: list[str] = []
    windows_found: int = 0
    deliveries_attempted: int = 0
    deliveries_suppressed: int = 0

    _collection: ClassVar = "runs"
    _indexes: ClassVar = [
        IndexModel([("started_at", DESCENDING)], name="started_at_desc"),
    ]


class AlertDoc(DbModel):
    alert_name: str = Field(index=True)
    local_date: str
    start: datetime
    end: datetime
    score: int
    classification: str
    first_seen_run_id: Id
    last_seen_run_id: Id
    seen_count: int = 1
    window: CandidateWindow

    _collection: ClassVar = "alerts"
    _indexes: ClassVar = [
        IndexModel(
            [("alert_name", ASCENDING), ("local_date", ASCENDING), ("start", ASCENDING)],
            name="alert_local_date_start",
        ),
    ]


class DeliveryDoc(DbModel):
    alert_id: Id
    run_id: Id
    channel_name: str
    channel_type: str
    status: DeliveryStatus
    error: str | None = None
    sent_at: datetime
    external_ref: str | None = None

    _collection: ClassVar = "deliveries"
    _indexes: ClassVar = [
        IndexModel(
            [("alert_id", ASCENDING), ("channel_name", ASCENDING), ("status", ASCENDING)],
            name="alert_channel_status",
        ),
    ]

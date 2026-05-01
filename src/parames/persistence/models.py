from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar, Literal

from pyodmongo import DbModel, Field, Id
from pymongo import ASCENDING, DESCENDING, IndexModel

from parames.common import LocationConfig
from parames.config import (
    DryConfig,
    ModelAgreementConfig,
    TimeWindowConfig,
    WindConfig,
)
from parames.domain import CandidateWindow, Classification
from parames.plugins.schemas import PluginConfig

RunStatus = Literal["running", "completed", "failed"]
DeliveryStatus = Literal["sent", "failed", "skipped"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AlertDefinition(DbModel):
    name: str = Field(index=True)
    description: str | None = None
    enabled: bool = True
    location: LocationConfig
    models: list[str]
    forecast_hours: int | None = None
    wind_level_m: int | None = None
    model_agreement: ModelAgreementConfig | None = None
    wind: WindConfig
    time_window: TimeWindowConfig | None = None
    dry: DryConfig | None = None
    plugins: list[PluginConfig] = []
    delivery: list[str]
    suppress_duplicates: bool | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    _collection: ClassVar = "alert_definitions"
    _indexes: ClassVar = [
        IndexModel([("name", ASCENDING)], name="alert_definition_name_unique", unique=True),
    ]


class Run(DbModel):
    started_at: datetime
    finished_at: datetime | None = None
    status: RunStatus = "running"
    error: str | None = None
    config_path: str
    alert_definition_ids: list[Id] = []
    windows_found: int = 0
    deliveries_attempted: int = 0
    deliveries_suppressed: int = 0

    _collection: ClassVar = "runs"
    _indexes: ClassVar = [
        IndexModel([("started_at", DESCENDING)], name="started_at_desc"),
    ]


class Detection(DbModel):
    alert_definition_id: Id
    alert_name: str = Field(index=True)
    local_date: str
    start: datetime
    end: datetime
    # 0–100 weighted-mean composite, or None when every signal opted out.
    score: int | None
    classification: Classification
    first_seen_run_id: Id
    last_seen_run_id: Id
    seen_count: int = 1
    window: CandidateWindow

    _collection: ClassVar = "detections"
    _indexes: ClassVar = [
        IndexModel(
            [("alert_name", ASCENDING), ("local_date", ASCENDING), ("start", ASCENDING)],
            name="alert_local_date_start",
        ),
        IndexModel([("alert_definition_id", ASCENDING)], name="alert_definition_id"),
    ]


class Delivery(DbModel):
    detection_id: Id
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
            [("detection_id", ASCENDING), ("channel_name", ASCENDING), ("status", ASCENDING)],
            name="detection_channel_status",
        ),
    ]

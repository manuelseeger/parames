from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from pyodmongo import AsyncDbEngine

from parames.domain import CandidateWindow
from parames.forecast import ZURICH_TIMEZONE
from parames.persistence.models import AlertDoc, DeliveryDoc, DeliveryStatus, RunDoc, RunStatus


def build_engine(mongo_uri: str) -> AsyncDbEngine:
    parsed = urlparse(mongo_uri)
    db_name = parsed.path.lstrip("/") or "parames"
    return AsyncDbEngine(mongo_uri=mongo_uri, db_name=db_name)


def local_date_for_window(window: CandidateWindow) -> str:
    return window.start.astimezone(ZoneInfo(ZURICH_TIMEZONE)).date().isoformat()


def is_same_event(prior: CandidateWindow, candidate: CandidateWindow) -> bool:
    """The dedupe heuristic in one place — must mirror the Mongo query in find_matching_alert."""
    if prior.alert_name != candidate.alert_name:
        return False
    if local_date_for_window(prior) != local_date_for_window(candidate):
        return False
    return prior.start < candidate.end and prior.end > candidate.start


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AlertRepository:
    def __init__(self, engine: AsyncDbEngine) -> None:
        self._engine = engine

    async def start_run(self, *, config_path: str, alert_names: list[str]) -> RunDoc:
        run = RunDoc(
            started_at=_utcnow(),
            status="running",
            config_path=config_path,
            alert_names=alert_names,
        )
        await self._engine.save(run)
        return run

    async def finish_run(
        self,
        run: RunDoc,
        *,
        status: RunStatus,
        error: str | None = None,
        windows_found: int,
        deliveries_attempted: int,
        deliveries_suppressed: int,
    ) -> None:
        run.finished_at = _utcnow()
        run.status = status
        run.error = error
        run.windows_found = windows_found
        run.deliveries_attempted = deliveries_attempted
        run.deliveries_suppressed = deliveries_suppressed
        await self._engine.save(run)

    async def find_matching_alert(
        self, alert_name: str, window: CandidateWindow
    ) -> AlertDoc | None:
        query = (
            (AlertDoc.alert_name == alert_name)
            & (AlertDoc.local_date == local_date_for_window(window))
            & (AlertDoc.start < window.end)
            & (AlertDoc.end > window.start)
        )
        return await self._engine.find_one(Model=AlertDoc, query=query)

    async def upsert_alert(
        self,
        window: CandidateWindow,
        *,
        run_id,
        existing: AlertDoc | None,
    ) -> AlertDoc:
        if existing is None:
            doc = AlertDoc(
                alert_name=window.alert_name,
                local_date=local_date_for_window(window),
                start=window.start,
                end=window.end,
                score=window.score,
                classification=window.classification,
                first_seen_run_id=run_id,
                last_seen_run_id=run_id,
                seen_count=1,
                window=window,
            )
        else:
            doc = existing
            doc.start = window.start
            doc.end = window.end
            doc.score = window.score
            doc.classification = window.classification
            doc.last_seen_run_id = run_id
            doc.seen_count += 1
            doc.window = window
        await self._engine.save(doc)
        return doc

    async def was_delivered(self, alert_id, channel_name: str) -> bool:
        query = (
            (DeliveryDoc.alert_id == alert_id)
            & (DeliveryDoc.channel_name == channel_name)
            & (DeliveryDoc.status == "sent")
        )
        existing = await self._engine.find_one(Model=DeliveryDoc, query=query)
        return existing is not None

    async def record_delivery(
        self,
        *,
        alert_id,
        run_id,
        channel_name: str,
        channel_type: str,
        status: DeliveryStatus,
        error: str | None = None,
        external_ref: str | None = None,
    ) -> DeliveryDoc:
        delivery = DeliveryDoc(
            alert_id=alert_id,
            run_id=run_id,
            channel_name=channel_name,
            channel_type=channel_type,
            status=status,
            error=error,
            sent_at=_utcnow(),
            external_ref=external_ref,
        )
        await self._engine.save(delivery)
        return delivery

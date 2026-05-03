from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from pyodmongo import AsyncDbEngine

from parames.domain import CandidateWindow
from parames.forecast import ZURICH_TIMEZONE
from parames.persistence.models import (
    AlertDefinition,
    Delivery,
    DeliveryStatus,
    Detection,
    Run,
    RunStatus,
)


def build_engine(mongo_uri: str) -> AsyncDbEngine:
    parsed = urlparse(mongo_uri)
    db_name = parsed.path.lstrip("/") or "parames"
    return AsyncDbEngine(mongo_uri=mongo_uri, db_name=db_name)


def local_date_for_window(window: CandidateWindow) -> str:
    return window.start.astimezone(ZoneInfo(ZURICH_TIMEZONE)).date().isoformat()


def is_same_event(prior: CandidateWindow, candidate: CandidateWindow) -> bool:
    """The dedupe heuristic in one place — must mirror the Mongo query in find_matching_detection."""
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

    # ------------- Alert definitions (CRUD) -------------

    async def list_alert_definitions(self, *, enabled_only: bool = False) -> list[AlertDefinition]:
        query = AlertDefinition.enabled == True if enabled_only else None  # noqa: E712
        results = await self._engine.find_many(Model=AlertDefinition, query=query)
        return list(results)

    async def get_alert_definition(self, definition_id) -> AlertDefinition | None:
        return await self._engine.find_one(
            Model=AlertDefinition, query=AlertDefinition.id == definition_id
        )

    async def get_alert_definition_by_name(self, name: str) -> AlertDefinition | None:
        return await self._engine.find_one(
            Model=AlertDefinition, query=AlertDefinition.name == name
        )

    async def create_alert_definition(self, definition: AlertDefinition) -> AlertDefinition:
        definition.created_at = _utcnow()
        definition.updated_at = definition.created_at
        await self._engine.save(definition)
        return definition

    async def update_alert_definition(self, definition: AlertDefinition) -> AlertDefinition:
        definition.updated_at = _utcnow()
        await self._engine.save(definition)
        return definition

    async def delete_alert_definition(self, definition_id) -> bool:
        response = await self._engine.delete(
            Model=AlertDefinition, query=AlertDefinition.id == definition_id
        )
        return getattr(response, "deleted_count", 0) > 0

    async def upsert_alert_definition(self, definition: AlertDefinition) -> AlertDefinition:
        """Idempotent create-or-replace by `name`. Used by the seed command."""
        existing = await self.get_alert_definition_by_name(definition.name)
        if existing is None:
            return await self.create_alert_definition(definition)
        definition.id = existing.id
        definition.created_at = existing.created_at
        return await self.update_alert_definition(definition)

    # ------------- Runs -------------

    async def start_run(
        self,
        *,
        config_path: str,
        alert_definition_ids: list,
        is_backtest: bool = False,
    ) -> Run:
        run = Run(
            started_at=_utcnow(),
            status="running",
            config_path=config_path,
            alert_definition_ids=alert_definition_ids,
            is_backtest=is_backtest,
        )
        await self._engine.save(run)
        return run

    async def finish_run(
        self,
        run: Run,
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

    async def list_runs(self, *, limit: int = 50) -> list[Run]:
        results = await self._engine.find_many(Model=Run, raw_sort={"started_at": -1})
        return list(results)[:limit]

    async def get_run(self, run_id) -> Run | None:
        return await self._engine.find_one(Model=Run, query=Run.id == run_id)

    # ------------- Detections (formerly alerts) -------------

    async def find_matching_detection(
        self, alert_name: str, window: CandidateWindow, *, is_backtest: bool = False
    ) -> Detection | None:
        query = (
            (Detection.alert_name == alert_name)
            & (Detection.local_date == local_date_for_window(window))
            & (Detection.start < window.end)
            & (Detection.end > window.start)
            & (Detection.is_backtest == is_backtest)
        )
        return await self._engine.find_one(Model=Detection, query=query)

    async def upsert_detection(
        self,
        window: CandidateWindow,
        *,
        alert_definition_id,
        run_id,
        existing: Detection | None,
        is_backtest: bool = False,
    ) -> Detection:
        if existing is None:
            doc = Detection(
                alert_definition_id=alert_definition_id,
                alert_name=window.alert_name,
                local_date=local_date_for_window(window),
                start=window.start,
                end=window.end,
                score=window.score,
                classification=window.classification,
                first_seen_run_id=run_id,
                last_seen_run_id=run_id,
                seen_count=1,
                is_backtest=is_backtest,
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

    async def list_detections(
        self, *, limit: int = 100, is_backtest: bool | None = None
    ) -> list[Detection]:
        query = None if is_backtest is None else (Detection.is_backtest == is_backtest)
        results = await self._engine.find_many(Model=Detection, query=query, raw_sort={"start": -1})
        return list(results)[:limit]

    async def get_detection(self, detection_id) -> Detection | None:
        return await self._engine.find_one(Model=Detection, query=Detection.id == detection_id)

    # ------------- Deliveries -------------

    async def was_delivered(self, detection_id, channel_name: str) -> bool:
        query = (
            (Delivery.detection_id == detection_id)
            & (Delivery.channel_name == channel_name)
            & (Delivery.status == "sent")
        )
        existing = await self._engine.find_one(Model=Delivery, query=query)
        return existing is not None

    async def record_delivery(
        self,
        *,
        detection_id,
        run_id,
        channel_name: str,
        channel_type: str,
        status: DeliveryStatus,
        error: str | None = None,
        external_ref: str | None = None,
    ) -> Delivery:
        delivery = Delivery(
            detection_id=detection_id,
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

    async def list_deliveries(self, *, limit: int = 100) -> list[Delivery]:
        results = await self._engine.find_many(Model=Delivery, raw_sort={"sent_at": -1})
        return list(results)[:limit]

    async def get_delivery(self, delivery_id) -> Delivery | None:
        return await self._engine.find_one(Model=Delivery, query=Delivery.id == delivery_id)

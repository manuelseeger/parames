from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from parames.config import RuntimeSettings
from parames.persistence import AlertRepository, build_engine
from parames.api.routers import alert_definitions, detections, deliveries, health, runs


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = RuntimeSettings()
    engine = build_engine(settings.mongo_uri)
    app.state.repo = AlertRepository(engine)
    yield


app = FastAPI(
    title="Parames API",
    description="Wind alert definitions, detections, runs, and deliveries.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(alert_definitions.router)
app.include_router(detections.router)
app.include_router(runs.router)
app.include_router(deliveries.router)

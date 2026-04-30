from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from parames.config import RuntimeSettings
from parames.persistence import AlertRepository, build_engine
from parames.api.routers import alert_definitions, detections, deliveries, health, runs


class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["cache-control"] = "no-store, no-cache, must-revalidate"
        return response


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
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.include_router(health.router, prefix="/api")
app.include_router(alert_definitions.router, prefix="/api")
app.include_router(detections.router, prefix="/api")
app.include_router(runs.router, prefix="/api")
app.include_router(deliveries.router, prefix="/api")

settings = RuntimeSettings()
WEBAPP_DIR = Path(__file__).resolve().parents[3] / "webapp" / "dist"
if WEBAPP_DIR.is_dir():
    static_cls = NoCacheStaticFiles if settings.dev_mode else StaticFiles
    app.mount("/", static_cls(directory=WEBAPP_DIR, html=True), name="webapp")

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from parames.config import RuntimeSettings, load_app_config
from parames.logging import LogRecorder
from parames.persistence import AlertRepository, build_engine
from parames.api.routers import alert_definitions, detections, deliveries, health, logs, runs


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
    config = load_app_config(settings.config_path)
    # MongoDB's TTL monitor removes expired documents automatically (usually within a minute).
    await engine._db["logs"].create_index("occurred_at", name="logs_ttl", expireAfterSeconds=config.logging.retention_days * 86400)
    recorder = LogRecorder(app.state.repo, "api")
    recorder.install()
    app.state.log_recorder = recorder
    try:
        yield
    finally:
        recorder.close()


app = FastAPI(
    title="Parames API",
    description="Wind alert definitions, detections, runs, and deliveries.",
    version="0.1.4",
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
app.include_router(logs.router, prefix="/api")

settings = RuntimeSettings()
WEBAPP_DIR = Path(__file__).resolve().parents[3] / "webapp" / "dist"
if WEBAPP_DIR.is_dir():
    static_cls = NoCacheStaticFiles if settings.dev_mode else StaticFiles
    app.mount("/", static_cls(directory=WEBAPP_DIR, html=True), name="webapp")

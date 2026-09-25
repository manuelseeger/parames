from __future__ import annotations

from contextlib import asynccontextmanager
from importlib.metadata import version
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from parames.api import auth
from parames.api.routers import alert_definitions, detections, deliveries, health, logs, runs
from parames.config import RuntimeSettings, load_app_config
from parames.logging import LogRecorder
from parames.persistence import AlertRepository, build_engine


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
    await app.state.repo.get_admin()
    for collection in ("alert_definitions", "detections"):
        if await engine._db[collection].count_documents({"owner_id": {"$exists": False}}, limit=1):
            raise RuntimeError("Legacy records need ownership. Run 'parames migrate-users' first.")
    indexes = await engine._db["alert_definitions"].index_information()
    if "owner_name_unique" not in indexes or "alert_definition_name_unique" in indexes:
        raise RuntimeError("Owner indexes are missing. Run 'parames migrate-users' first.")
    await engine._db["users"].create_index("email", unique=True, name="user_email_unique")
    await engine._db["sessions"].create_index("token_digest", unique=True, name="session_digest_unique")
    await engine._db["sessions"].create_index("expires_at", expireAfterSeconds=0, name="session_expiry")
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
    version=version("parames"),
    lifespan=lifespan,
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

@app.middleware("http")
async def enforce_origin(request, call_next):
    if request.url.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if not auth.same_origin(request):
            return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
    return await call_next(request)


app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
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

import asyncio
import logging


from apscheduler.schedulers.asyncio import AsyncIOScheduler
from parames.cli import _run
from parames.config import RuntimeSettings

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

def _default_config_path():
    return RuntimeSettings().config_path



async def main() -> None:
    settings = RuntimeSettings()

    scheduler = AsyncIOScheduler(timezone="Europe/Zurich")

    # Build job trigger - use minute if configured, otherwise just hour
    job_kwargs = {
        "id": "main_job",
        "replace_existing": True,
        "kwargs": {"config_path": _default_config_path()},
        "max_instances": 1,
        "coalesce": True,
    }

    if settings.scheduler.cron_minute:
        scheduler.add_job(_run, "cron", minute=settings.scheduler.cron_minute, **job_kwargs)
    else:
        scheduler.add_job(_run, "cron", hour=settings.scheduler.cron_hour, **job_kwargs)


    logger.info("Starting scheduler with config path: %s", _default_config_path())
    logger.info("Scheduler will run with cron_hour=%s and cron_minute=%s", settings.scheduler.cron_hour, settings.scheduler.cron_minute)
    scheduler.start()

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Stopping scheduler...")
        scheduler.shutdown(wait=False)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
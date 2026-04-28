import asyncio
import logging


from apscheduler.schedulers.asyncio import AsyncIOScheduler
from parames.cli import _run
from parames.config import RuntimeSettings, load_app_config

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

def _default_config_path():
    return RuntimeSettings().config_path

async def main() -> None:
    config_path  = _default_config_path()
    app_config = load_app_config(config_path)

    scheduler = AsyncIOScheduler(timezone="Europe/Zurich")

    scheduler.add_job(
        _run,
        "cron",
        hour=app_config.scheduler.cron_hour,
        #minute="*/1",
        id="main_job",
        replace_existing=True,
        kwargs={"config_path": _default_config_path()},
        max_instances=1,
        coalesce=True,
    )


    logger.info("Starting scheduler with config path: %s", _default_config_path())
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
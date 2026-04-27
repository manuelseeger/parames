from apscheduler.schedulers.blocking import BlockingScheduler
from parames.cli import _run
from parames.config import RuntimeSettings


def _default_config_path():
    """Get default config path, matching CLI behavior."""
    return RuntimeSettings().config_path


scheduler = BlockingScheduler(timezone="Europe/Zurich")

scheduler.add_job(
    _run,
    "cron",
    hour="*/6",  # Run every 6 hours
    id="main_job",
    replace_existing=True,
    kwargs={"config_path": _default_config_path()},
)

if __name__ == "__main__":
    scheduler.start()
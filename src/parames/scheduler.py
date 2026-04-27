from apscheduler.schedulers.blocking import BlockingScheduler
from parames.cli import _run

scheduler = BlockingScheduler(timezone="Europe/Zurich")

scheduler.add_job(
    _run,
    "cron",
    minute="*/15",
    id="main_job",
    replace_existing=True,
)

scheduler.start()
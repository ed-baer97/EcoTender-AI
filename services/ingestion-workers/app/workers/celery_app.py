import os

from celery import Celery
from celery.schedules import crontab

celery_app = Celery(
    "ecotender_ingest",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2"),
    include=["app.workers.tasks"],
)

celery_app.conf.task_routes = {
    "app.workers.tasks.*": {"queue": "ingest"},
}
celery_app.conf.timezone = "UTC"

if os.getenv("GOSZAKUP_DAILY_ENABLED", "true").lower() in {"1", "true", "yes", "on"}:
    minute = int(os.getenv("GOSZAKUP_DAILY_MINUTE", "0"))
    hour = int(os.getenv("GOSZAKUP_DAILY_HOUR", "3"))
    source_code = os.getenv("GOSZAKUP_DAILY_SOURCE_CODE", "KZ_GOSZAKUP_PLAYWRIGHT")
    celery_app.conf.beat_schedule = {
        "goszakup-daily-crawl": {
            "task": "app.workers.tasks.crawl_source",
            "schedule": crontab(minute=minute, hour=hour),
            "args": (source_code,),
            "options": {"queue": "ingest"},
        }
    }

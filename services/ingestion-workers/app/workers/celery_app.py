import os

from celery import Celery

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

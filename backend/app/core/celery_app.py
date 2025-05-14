from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.video"],
)

celery_app.conf.task_routes = {
    "app.tasks.video.process_video": {"queue": "videos"},
}

celery_app.conf.update(
    task_track_started=True,
    worker_send_task_events=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
)

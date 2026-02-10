from celery import Celery
from app.core.config import settings

celery_app = Celery("tasks", broker=settings.REDIS_URL)

@celery_app.task
def add(x, y):
    return x + y

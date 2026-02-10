from app.tasks.sample_task import celery_app

celery_app.worker_main(["worker", "--loglevel=info"])

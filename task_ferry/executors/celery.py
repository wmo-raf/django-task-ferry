from .base import BaseExecutor


class CeleryExecutor(BaseExecutor):
    """
    Dispatches jobs via Celery.

    Requires celery to be installed:
        pip install django-task-ferry[celery]

    Configure in Django settings:
        TASK_FERRY = {
            "EXECUTOR": "task_ferry.executors.celery.CeleryExecutor",
            "CELERY_QUEUE": "default",   # optional, defaults to "default"
        }

    The dispatch is wrapped in transaction.on_commit so the job record
    is guaranteed to be visible to the worker before it starts.
    """

    def enqueue(self, job_id: int) -> None:
        from django.db import transaction

        from task_ferry.conf import get_setting
        from task_ferry.tasks import run_async_job

        queue = get_setting("CELERY_QUEUE")

        def _dispatch():
            run_async_job.apply_async(args=[job_id], queue=queue)

        transaction.on_commit(_dispatch)

"""
Generic Celery task for executing any registered job type.

This module is only imported when Celery is installed and the
CeleryExecutor is configured. It must not be imported at module
level from any code path that runs without Celery.
"""

from __future__ import annotations

try:
    from celery import shared_task
except ImportError as e:
    raise ImportError(
        "celery is not installed. "
        "Install it with: pip install django-task-ferry[celery]"
    ) from e


@shared_task(bind=True, acks_late=True, max_retries=0, ignore_result=True)
def run_async_job(self, job_id: int) -> None:
    """
    Entry point for all async job execution via Celery.

    Loads the job by ID and delegates to JobHandler.run().
    State transitions and progress tracking are fully managed
    by the handler — this task stays thin on purpose.

    :param job_id: PK of the Job record to run.
    """
    from task_ferry.handler import JobHandler

    JobHandler.run_by_id(job_id)

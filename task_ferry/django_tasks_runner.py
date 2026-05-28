"""
django-tasks runner for django-task-ferry.

This module is only imported when django-tasks (DEP-0014) is installed
and the DjangoTasksExecutor is configured.

Usage in settings:
    TASK_FERRY = {
        "EXECUTOR": "task_ferry.executors.django_tasks.DjangoTasksExecutor",
    }

    TASKS = {
        "default": {
            "BACKEND": "django_tasks.backends.database.DatabaseBackend",
        }
    }
"""

from __future__ import annotations

try:
    from django_tasks import task
except ImportError as e:
    raise ImportError(
        "django-tasks is not installed. "
        "Install it with: pip install django-task-ferry[django-tasks]"
    ) from e


@task()
def run_job_via_django_tasks(job_id: int) -> None:
    """
    Entry point for all async job execution via django-tasks.

    Loads the job by ID and delegates to JobHandler.run().
    State transitions and progress tracking are fully managed
    by the handler — this task stays thin on purpose.

    :param job_id: PK of the Job record to run.
    """
    from task_ferry.handler import JobHandler

    JobHandler.run_by_id(job_id)

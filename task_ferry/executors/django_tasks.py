from .base import BaseExecutor


class DjangoTasksExecutor(BaseExecutor):
    """
    Dispatches jobs via django-tasks (DEP-0014 backport).

    Requires django-tasks to be installed:
        pip install django-task-ferry[django-tasks]

    Configure in Django settings:
        TASK_FERRY = {
            "EXECUTOR": "task_ferry.executors.django_tasks.DjangoTasksExecutor",
        }

    Also configure a django-tasks backend in TASKS:
        TASKS = {
            "default": {
                "BACKEND": "django_tasks.backends.database.DatabaseBackend",
            }
        }
    """

    def enqueue(self, job_id: int) -> None:
        try:
            from task_ferry.django_tasks_runner import run_job_via_django_tasks
        except ImportError as e:
            raise ImportError(
                "django-tasks is not installed. "
                "Install it with: pip install django-task-ferry[django-tasks]"
            ) from e

        run_job_via_django_tasks.enqueue(job_id)

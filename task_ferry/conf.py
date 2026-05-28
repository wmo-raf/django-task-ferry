"""
Package-level settings with sane defaults.

Override any key in your Django settings:

    TASK_FERRY = {
        "EXECUTOR": "task_ferry.executors.celery.CeleryExecutor",
        "CELERY_QUEUE": "default",
        "PROGRESS_CACHE_TIMEOUT": 3600,
        "JOB_EXPIRY_DAYS": 7,
        "MAX_JOBS_PER_USER_PER_TYPE": 5,
    }
"""

from django.conf import settings

DEFAULTS = {
    # Dotted path to the executor class used to dispatch jobs.
    "EXECUTOR": "task_ferry.executors.immediate.ImmediateExecutor",
    # Celery queue name (used by CeleryExecutor only).
    "CELERY_QUEUE": "default",
    # How long (seconds) to keep progress data in the cache.
    # Cached progress is the authoritative source mid-transaction.
    "PROGRESS_CACHE_TIMEOUT": 3600,
    # Jobs older than this many days are deleted by cleanup.
    "JOB_EXPIRY_DAYS": 7,
    # Default maximum concurrent jobs of one type per user.
    # Individual JobType subclasses can override this.
    "MAX_JOBS_PER_USER_PER_TYPE": 5,
}


def get_setting(key: str):
    user_config = getattr(settings, "TASK_FERRY", {})
    return user_config.get(key, DEFAULTS[key])


def get_executor():
    """Import and return the configured executor instance."""
    from importlib import import_module

    from .exceptions import ExecutorNotConfigured

    dotted_path = get_setting("EXECUTOR")
    try:
        module_path, class_name = dotted_path.rsplit(".", 1)
        module = import_module(module_path)
        cls = getattr(module, class_name)
        return cls()
    except (ImportError, AttributeError, ValueError) as e:
        raise ExecutorNotConfigured(
            f"Could not load TASK_FERRY executor '{dotted_path}': {e}"
        ) from e

from django.apps import AppConfig


class TaskFerryConfig(AppConfig):
    name = "task_ferry"
    verbose_name = "Task Ferry"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Ensure the executor is initialised on startup so
        # any misconfiguration is caught early.
        from .conf import get_executor  # noqa: F401

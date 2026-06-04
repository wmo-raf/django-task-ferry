from .base import BaseExecutor


class ImmediateExecutor(BaseExecutor):
    """
    Runs jobs synchronously in the current process.

    This is the default executor and is ideal for:
    - Tests (no broker or worker needed)
    - Development environments
    - Simple scripts and management commands

    Configure in Django settings (or test settings):
        TASK_FERRY = {
            "EXECUTOR": "task_ferry.executors.immediate.ImmediateExecutor",
        }

    Jobs run inline — enqueue() blocks until the job completes.
    Exceptions propagate to the caller rather than marking the job failed,
    so test assertions can catch them directly.
    """

    def enqueue(self, job_id: int, queue: str | None = None) -> None:
        from task_ferry.handler import JobHandler

        JobHandler.run_by_id(job_id)

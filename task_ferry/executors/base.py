from abc import ABC, abstractmethod


class BaseExecutor(ABC):
    """
    Interface between the job tracking layer and whatever mechanism
    actually runs jobs in the background.

    The contract is minimal by design — the executor only needs to
    schedule a job by ID. The package's generic task handles the rest.
    """

    @abstractmethod
    def enqueue(self, job_id: int, queue: str | None = None) -> None:
        """
        Schedule the job with the given ID to be executed.

        The job must already be saved to the database before this is called
        (JobHandler.create_and_start ensures this). The implementation
        should call task_ferry's generic run task with the job_id.

        Implementations must be safe to call inside a Django transaction —
        the actual dispatch should happen on_commit where possible.
        """
        raise NotImplementedError

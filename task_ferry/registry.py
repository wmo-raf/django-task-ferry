"""
JobType registry.

Define a job type by subclassing JobType, setting `type` and `model_class`,
and implementing `run(job, progress)`. Register it in your AppConfig.ready():

    from task_ferry.registry import job_type_registry
    from .job_types import MyJobType

    job_type_registry.register(MyJobType())

The run() method receives the concrete job instance and a Progress object
rooted at 100. Call progress.increment(by=N, state="...") as work proceeds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type

if TYPE_CHECKING:
    from .models import Job
    from .progress import Progress


class JobType:
    """
    Base class for all job types.

    Subclass and implement at minimum:
        type        — unique string identifier, e.g. "ingestion"
        model_class — the Job subclass for this type
        run()       — the actual work
    """

    # ── Required ───────────────────────────────────────────────────────────────

    type: str = ""
    """Unique string identifier for this job type."""

    model_class: Optional[Type["Job"]] = None
    """The Job subclass whose DB table stores this type's extra fields."""

    # ── Optional overrides ─────────────────────────────────────────────────────

    max_count: int = 5
    """
    Maximum number of pending-or-running jobs of this type per user.
    Override to 1 for jobs where duplicates make no sense (e.g. re-ingestion
    of the same file), or higher for workloads that parallelise naturally.
    """

    queue: Optional[str] = None
    """
    Queue name to route this job type to. When None, falls back to the
    global TASK_FERRY["CELERY_QUEUE"] setting (CeleryExecutor only).
    """

    def prepare_values(self, values: Dict[str, Any], user: Any) -> Dict[str, Any]:
        """
        Validate and transform request values before the job model is created.

        This is the right place to:
        - Resolve IDs to model instances
        - Check domain permissions
        - Raise validation errors before the job is persisted

        :param values: Raw values from the API or create_and_start call.
        :param user:   The requesting user (may be None for system jobs).
        :return:       Cleaned values used as kwargs when creating model_class.
        """
        return values

    def after_job_creation(self, job: "Job", values: Dict[str, Any]) -> None:
        """
        Hook called immediately after the job model is saved for the first time.
        Useful for attaching related objects (e.g. M2M) that need the PK to exist.
        """

    def run(self, job: "Job", progress: "Progress") -> Any:
        """
        The actual work. Runs inside a Celery task (or whichever executor
        is configured). Called inside a try/except — unhandled exceptions
        will mark the job as failed.

        Call progress.increment(by=N, state="...") periodically so the
        frontend sees meaningful updates. Check job.is_cancelled periodically
        and raise JobCancelled() if you want to support cooperative cancellation.

        :param job:      The specific (concrete subclass) job instance.
        :param progress: A Progress object rooted at 100.
        :return:         Anything — the return value is not persisted but is
                         returned from JobHandler.run() for synchronous callers.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement run(job, progress)."
        )

    def on_error(self, job: "Job", exc: Exception) -> None:
        """
        Called after a job failure, outside the transaction.
        Override to clean up temp files, notify monitoring, etc.
        """

    def on_cancelled(self, job: "Job") -> None:
        """
        Called after a job is cancelled, outside the transaction.
        """

    def before_delete(self, job: "Job") -> None:
        """
        Called before a job record is deleted (e.g. by cleanup).
        Override to remove associated files or external resources.
        """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Validate that concrete subclasses define the required attributes.
        if cls.type == "" or cls.model_class is None:
            return  # allow intermediate abstract subclasses
        if not cls.type:
            raise TypeError(f"{cls.__name__} must define a non-empty 'type' string.")
        if cls.model_class is None:
            raise TypeError(f"{cls.__name__} must define 'model_class'.")


# ── Registry ───────────────────────────────────────────────────────────────────


class _JobTypeRegistry:
    def __init__(self) -> None:
        self._by_type: Dict[str, JobType] = {}
        self._by_model: Dict[Type, JobType] = {}

    def register(self, job_type: JobType) -> JobType:
        """
        Register a JobType instance.
        Usually called from AppConfig.ready().
        """
        if not job_type.type:
            raise ValueError("JobType.type must be a non-empty string.")
        if job_type.model_class is None:
            raise ValueError("JobType.model_class must be set.")
        if job_type.type in self._by_type:
            raise ValueError(
                f"A job type with type='{job_type.type}' is already registered."
            )
        self._by_type[job_type.type] = job_type
        self._by_model[job_type.model_class] = job_type
        return job_type

    def get(self, type_name: str) -> JobType:
        """Look up a registered JobType by its string identifier."""
        from .exceptions import JobTypeNotRegistered

        try:
            return self._by_type[type_name]
        except KeyError:
            raise JobTypeNotRegistered(
                f"No job type registered for '{type_name}'. "
                f"Available: {list(self._by_type.keys())}"
            )

    def get_by_model(self, job: "Job") -> JobType:
        """Look up the JobType for a given job instance."""
        from .exceptions import JobTypeNotRegistered

        model_class = type(job)
        # Walk the MRO so that direct subclasses of abstract intermediaries work.
        for cls in model_class.__mro__:
            if cls in self._by_model:
                return self._by_model[cls]
        raise JobTypeNotRegistered(
            f"No job type registered for model '{model_class.__name__}'."
        )

    def all(self) -> List[JobType]:
        """Return all registered JobType instances."""
        return list(self._by_type.values())

    def __repr__(self) -> str:
        return f"<JobTypeRegistry types={list(self._by_type.keys())}>"


job_type_registry: _JobTypeRegistry = _JobTypeRegistry()

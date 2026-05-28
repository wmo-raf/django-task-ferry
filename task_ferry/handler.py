"""
JobHandler — the single place all job lifecycle operations go through.

Consumers should call:
    JobHandler.create_and_start(user, "my_type", field=value, ...)
    JobHandler.get_job(user, job_id)
    JobHandler.cancel(user, job_id)

The handler is responsible for:
 - Validating and creating the job model instance
 - Dispatching to the configured executor
 - Running the job (called from within the executor task)
 - Enforcing max_count limits per user per type
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, Optional, Type

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from .conf import get_executor, get_setting
from .exceptions import JobDoesNotExist, JobNotCancellable, MaxJobCountExceeded
from .models import Job, JOB_CANCELLED
from .progress import Progress
from .registry import job_type_registry

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


class JobHandler:
    
    @classmethod
    def create_and_start(
            cls,
            user: Optional["AbstractUser"],
            job_type_name: str,
            **kwargs: Any,
    ) -> Job:
        """
        Create a job of the given type and schedule it for execution.

        :param user:          The user triggering the job. May be None for
                              system/automated jobs.
        :param job_type_name: The registered JobType.type string.
        :param kwargs:        Passed to JobType.prepare_values() for validation
                              and transformation before the model is created.
        :returns:             The saved Job instance (concrete subclass).
        """
        job_type = job_type_registry.get(job_type_name)
        model_class = job_type.model_class
        
        # Validate and transform input values.
        values = job_type.prepare_values(kwargs, user)
        
        # Enforce max concurrent jobs of this type for this user.
        if user is not None:
            running = (
                model_class.objects.filter(user=user)
                .pending_or_running()
                .count()
            )
            if running >= job_type.max_count:
                raise MaxJobCountExceeded(
                    f"You can have at most {job_type.max_count} concurrent "
                    f"'{job_type_name}' job(s). Wait for one to finish first."
                )
        
        job = model_class(
            user=user,
            # for_concrete_model=False ensures proxy models get their own
            # ContentType entry — required for .specific to resolve correctly.
            content_type=ContentType.objects.get_for_model(
                model_class, for_concrete_model=False
            ),
            **values,
        )
        job.save()
        job_type.after_job_creation(job, kwargs)
        
        # Dispatch — executor handles on_commit wrapping where needed.
        get_executor().enqueue(job.id)
        
        return job
    
    @classmethod
    def run_by_id(cls, job_id: int) -> Any:
        """
        Load the job by ID and run it. Called from within the executor task.
        """
        job = Job.objects.get(id=job_id).specific
        return cls.run(job)
    
    @classmethod
    def run(cls, job: Job) -> Any:
        """
        Execute a job. Manages state transitions and the Progress callback.

        Called from the Celery task (or ImmediateExecutor).
        Should not be called directly by consuming code.
        """
        from .exceptions import JobCancelled as _JobCancelled
        
        job_type = job_type_registry.get_by_model(job)
        
        if job.is_cancelled:
            job_type.on_cancelled(job)
            job.clear_cache()
            return None
        
        job.mark_started()
        
        def on_progress(pct: int, label: str) -> None:
            # Cooperative cancellation check on every progress update.
            if job.get_cached_state() == JOB_CANCELLED:
                raise _JobCancelled()
            job.set_progress(pct, label)
        
        progress = Progress(total=100)
        progress.register_updated_event(on_progress)
        
        try:
            result = job_type.run(job, progress)
            job.mark_finished()
            return result
        except _JobCancelled:
            job.mark_cancelled()
            job_type.on_cancelled(job)
            return None
        except Exception as exc:
            job.mark_failed(
                error=str(exc),
                human_readable_error=f"An error occurred while running the job: {exc}",
            )
            job_type.on_error(job, exc)
            raise
        finally:
            job.clear_cache()
    
    @classmethod
    def get_job(
            cls,
            user: Optional["AbstractUser"],
            job_id: int,
            model_class: Optional[Type[Job]] = None,
    ) -> Job:
        """
        Fetch a job by ID, scoped to the given user.

        :param user:        If provided, the job must belong to this user.
                            Pass None to fetch system jobs without ownership check.
        :param job_id:      The job PK.
        :param model_class: Optional concrete model class for type-safe queries.
        """
        qs = (model_class or Job).objects
        filters: dict = {"id": job_id}
        if user is not None:
            filters["user"] = user
        try:
            return qs.get(**filters)
        except Job.DoesNotExist:
            raise JobDoesNotExist(f"Job {job_id} does not exist.")
    
    @classmethod
    def cancel(
            cls,
            user: Optional["AbstractUser"],
            job_id: int,
    ) -> Job:
        """
        Mark a job for cancellation.

        Cancellation is cooperative — running jobs check job.is_cancelled
        via the progress callback and raise JobCancelled when detected.

        :raises JobDoesNotExist:   Job not found for this user.
        :raises JobNotCancellable: Job has already ended.
        """
        job = cls.get_job(user, job_id)
        # Check idempotency first — a cancelled job is technically "ended"
        # so the has_ended guard must come after the is_cancelled short-circuit.
        if job.is_cancelled:
            return job  # idempotent
        if job.has_ended:
            raise JobNotCancellable(
                f"Job {job_id} has already ended with state '{job.state}'."
            )
        job.mark_cancelled()
        return job
    
    @classmethod
    def get_jobs_for_user(
            cls,
            user: "AbstractUser",
            states: Optional[list] = None,
            job_type_name: Optional[str] = None,
            limit: int = 50,
            offset: int = 0,
    ):
        """
        Return jobs for the given user, optionally filtered by state/type.
        """
        model_class = Job
        if job_type_name:
            jt = job_type_registry.get(job_type_name)
            model_class = jt.model_class
        
        qs = model_class.objects.filter(user=user)
        
        if states:
            qs = qs.filter(state__in=states)
        
        return qs.select_related("content_type", "user")[offset: offset + limit]
    
    @classmethod
    def cleanup_old_jobs(cls) -> int:
        """
        Delete ended jobs older than JOB_EXPIRY_DAYS.
        Calls JobType.before_delete() for each. Returns count deleted.
        """
        cutoff = timezone.now() - timedelta(days=get_setting("JOB_EXPIRY_DAYS"))
        old_jobs = Job.objects.ended().filter(created_at__lt=cutoff)
        count = 0
        for job in old_jobs.select_related("content_type"):
            try:
                specific = job.specific
                job_type = job_type_registry.get_by_model(specific)
                job_type.before_delete(specific)
            except Exception:
                pass  # don't let cleanup hooks abort the whole run
            job.clear_cache()
            job.delete()
            count += 1
        return count

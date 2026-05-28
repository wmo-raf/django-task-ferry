"""
Job base model.

Each concrete job type subclasses Job and adds its own domain-specific
fields. Django's multi-table inheritance handles the per-type table.

Progress is written to the cache (Redis) mid-transaction and only
persisted to the DB when the transaction commits. This is required
because no other DB connection can read uncommitted progress values.
The API endpoints read from cache first, falling back to the DB.
"""

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import models
from django.utils import timezone

from .conf import get_setting

User = get_user_model()

# ── State constants ────────────────────────────────────────────────────────────

JOB_PENDING = "pending"
JOB_STARTED = "started"
JOB_FINISHED = "finished"
JOB_FAILED = "failed"
JOB_CANCELLED = "cancelled"

JOB_STATES_ENDED = (JOB_FINISHED, JOB_FAILED, JOB_CANCELLED)
JOB_STATES_RUNNING = (JOB_STARTED,)
JOB_STATES_PENDING_OR_RUNNING = (JOB_PENDING, JOB_STARTED)


def _cache_key(job_id: int) -> str:
    return f"task_ferry:job:{job_id}:progress"


# ── QuerySet ───────────────────────────────────────────────────────────────────


class JobQuerySet(models.QuerySet):
    def pending_or_running(self):
        return self.filter(state__in=JOB_STATES_PENDING_OR_RUNNING)

    def ended(self):
        return self.filter(state__in=JOB_STATES_ENDED)


# ── Base model ─────────────────────────────────────────────────────────────────


class Job(models.Model):
    """
    Base model for all job types.

    Subclass this in your app and add domain-specific fields:

        class MyJob(Job):
            input_file = models.CharField(max_length=500)
            items_created = models.IntegerField(default=0)

    Register the corresponding JobType in your AppConfig.ready():

        from task_ferry.registry import job_type_registry
        job_type_registry.register(MyJobType())
    """

    # ContentType lets us resolve job.specific without knowing the concrete type.
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="task_ferry_jobs",
    )
    # Optional — system-triggered jobs (e.g. automated ingestion) may have no user.
    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="task_ferry_jobs",
    )
    state = models.CharField(
        max_length=32,
        default=JOB_PENDING,
        db_index=True,
        help_text="Current lifecycle state of the job.",
    )
    progress_percentage = models.IntegerField(
        default=0,
        help_text="0–100. Updated via cache mid-run; persisted to DB at completion.",
    )
    progress_state = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Human-readable description of the current step.",
    )
    error = models.TextField(
        blank=True,
        default="",
        help_text="Short error string (exception message).",
    )
    human_readable_error = models.TextField(
        blank=True,
        default="",
        help_text="Longer, user-facing error description.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = JobQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)

    # ── Cache ──────────────────────────────────────────────────────────────────

    def _read_cache(self) -> dict:
        return cache.get(_cache_key(self.id)) or {}

    def _write_cache(self) -> None:
        cache.set(
            _cache_key(self.id),
            {
                "progress_percentage": self.progress_percentage,
                "progress_state": self.progress_state,
                "state": self.state,
                "updated_at": timezone.now().isoformat(),
            },
            timeout=get_setting("PROGRESS_CACHE_TIMEOUT"),
        )

    def clear_cache(self) -> None:
        cache.delete(_cache_key(self.id))

    def get_cached_progress_percentage(self) -> int:
        return self._read_cache().get("progress_percentage", self.progress_percentage)

    def get_cached_state(self) -> str:
        return self._read_cache().get("state", self.state)

    def get_cached_progress_state(self) -> str:
        return self._read_cache().get("progress_state", self.progress_state)

    # ── Progress update (called from inside the worker) ────────────────────────

    def set_progress(self, percentage: int, state_label: str = "") -> None:
        """
        Update progress. Writes to Redis immediately — DB not touched.
        Called frequently from within the running job.
        """
        self.progress_percentage = max(0, min(100, percentage))
        if state_label:
            self.progress_state = state_label
        self._write_cache()

    # ── State transitions ──────────────────────────────────────────────────────

    def mark_started(self) -> None:
        self.state = JOB_STARTED
        self._write_cache()
        self.save(update_fields=["state", "updated_at"])

    def mark_finished(self) -> None:
        self.state = JOB_FINISHED
        self.progress_percentage = 100
        self._write_cache()
        self.save(update_fields=["state", "progress_percentage", "updated_at"])

    def mark_failed(self, error: str, human_readable_error: str = "") -> None:
        self.state = JOB_FAILED
        self.error = error
        self.human_readable_error = human_readable_error or error
        self._write_cache()
        self.save(
            update_fields=["state", "error", "human_readable_error", "updated_at"]
        )

    def mark_cancelled(self) -> None:
        self.state = JOB_CANCELLED
        self._write_cache()
        self.save(update_fields=["state", "updated_at"])

    # ── Convenience properties ─────────────────────────────────────────────────

    @property
    def is_pending(self) -> bool:
        return self.get_cached_state() == JOB_PENDING

    @property
    def is_running(self) -> bool:
        return self.get_cached_state() == JOB_STARTED

    @property
    def is_finished(self) -> bool:
        return self.get_cached_state() == JOB_FINISHED

    @property
    def is_failed(self) -> bool:
        return self.get_cached_state() == JOB_FAILED

    @property
    def is_cancelled(self) -> bool:
        return self.get_cached_state() == JOB_CANCELLED

    @property
    def has_ended(self) -> bool:
        return self.get_cached_state() in JOB_STATES_ENDED

    # ── Polymorphic resolution ─────────────────────────────────────────────────

    @property
    def specific(self) -> "Job":
        """
        Return the concrete subclass instance.

        If self is already the concrete type, return self directly.
        Otherwise fetch the subclass row from its own table.
        """
        model_class = self.content_type.model_class()
        if isinstance(self, model_class):
            return self
        return model_class.objects.get(pk=self.pk)

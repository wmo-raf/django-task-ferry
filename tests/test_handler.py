"""
Tests for JobHandler: create_and_start, run, cancel, get_job, cleanup.

All tests use ImmediateExecutor (configured in conftest) so jobs run
synchronously — no broker or worker needed.
"""

from __future__ import annotations

import pytest

from task_ferry.exceptions import (
    JobDoesNotExist,
    JobNotCancellable,
    MaxJobCountExceeded,
)
from task_ferry.handler import JobHandler
from task_ferry.models import (
    JOB_CANCELLED,
    JOB_FAILED,
    JOB_FINISHED,
    JOB_PENDING,
    Job,
)


# ---------------------------------------------------------------------------
# create_and_start
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_create_and_start_runs_job(noop_job_type, user):
    job = JobHandler.create_and_start(user, "noop")
    job.refresh_from_db()
    assert job.state == JOB_FINISHED


@pytest.mark.django_db
def test_create_and_start_no_user(noop_job_type):
    """System jobs (user=None) should skip the max_count check."""
    job = JobHandler.create_and_start(None, "noop")
    job.refresh_from_db()
    assert job.state == JOB_FINISHED


@pytest.mark.django_db
def test_max_count_exceeded_raises(noop_job_type, user, monkeypatch):
    """
    When a user already has max_count pending/running jobs,
    create_and_start should raise MaxJobCountExceeded.
    """
    # Patch the executor so jobs stay PENDING (don't run immediately).
    from task_ferry.executors.immediate import ImmediateExecutor

    monkeypatch.setattr(ImmediateExecutor, "enqueue", lambda self, job_id: None)

    # Create exactly max_count jobs.
    for _ in range(noop_job_type.max_count):
        JobHandler.create_and_start(user, "noop")

    with pytest.raises(MaxJobCountExceeded):
        JobHandler.create_and_start(user, "noop")


# ---------------------------------------------------------------------------
# run / error handling
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_failing_job_marks_failed(failing_job_type, user):
    with pytest.raises(ValueError, match="boom"):
        JobHandler.create_and_start(user, "failing")

    job = Job.objects.filter(user=user).first()
    assert job.state == JOB_FAILED
    assert "boom" in job.error


@pytest.mark.django_db
def test_cancelled_before_run_is_handled(noop_job_type, user, monkeypatch):
    """
    If a job is cancelled before the executor picks it up,
    run() should call on_cancelled and return None.
    """
    from task_ferry.executors.immediate import ImmediateExecutor

    # Prevent immediate execution so we can cancel first.
    monkeypatch.setattr(ImmediateExecutor, "enqueue", lambda self, job_id: None)

    job = JobHandler.create_and_start(user, "noop")
    job.mark_cancelled()

    result = JobHandler.run(job)
    assert result is None


# ---------------------------------------------------------------------------
# get_job
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_get_job_returns_job(noop_job_type, user):
    job = JobHandler.create_and_start(user, "noop")
    fetched = JobHandler.get_job(user, job.id)
    assert fetched.id == job.id


@pytest.mark.django_db
def test_get_job_wrong_user_raises(noop_job_type, user, other_user):
    job = JobHandler.create_and_start(user, "noop")
    with pytest.raises(JobDoesNotExist):
        JobHandler.get_job(other_user, job.id)


@pytest.mark.django_db
def test_get_job_missing_raises(noop_job_type, user):
    with pytest.raises(JobDoesNotExist):
        JobHandler.get_job(user, 99999)


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_cancel_pending_job(noop_job_type, user, monkeypatch):
    from task_ferry.executors.immediate import ImmediateExecutor

    monkeypatch.setattr(ImmediateExecutor, "enqueue", lambda self, job_id: None)

    job = JobHandler.create_and_start(user, "noop")
    assert job.state == JOB_PENDING

    cancelled = JobHandler.cancel(user, job.id)
    assert cancelled.state == JOB_CANCELLED


@pytest.mark.django_db
def test_cancel_finished_job_raises(noop_job_type, user):
    job = JobHandler.create_and_start(user, "noop")
    job.refresh_from_db()
    assert job.state == JOB_FINISHED

    with pytest.raises(JobNotCancellable):
        JobHandler.cancel(user, job.id)


@pytest.mark.django_db
def test_cancel_idempotent(noop_job_type, user, monkeypatch):
    from task_ferry.executors.immediate import ImmediateExecutor

    monkeypatch.setattr(ImmediateExecutor, "enqueue", lambda self, job_id: None)

    job = JobHandler.create_and_start(user, "noop")
    JobHandler.cancel(user, job.id)
    # Second cancel should not raise.
    job2 = JobHandler.cancel(user, job.id)
    assert job2.state == JOB_CANCELLED


# ---------------------------------------------------------------------------
# cleanup_old_jobs
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_cleanup_old_jobs_deletes_expired(noop_job_type, user):
    from datetime import timedelta

    from django.utils import timezone

    job = JobHandler.create_and_start(user, "noop")
    job.refresh_from_db()

    # Backdate the job so it looks old enough to expire.
    Job.objects.filter(pk=job.pk).update(
        created_at=timezone.now() - timedelta(days=30)
    )

    deleted = JobHandler.cleanup_old_jobs()
    assert deleted >= 1
    assert not Job.objects.filter(pk=job.pk).exists()


@pytest.mark.django_db
def test_cleanup_does_not_delete_recent_jobs(noop_job_type, user):
    job = JobHandler.create_and_start(user, "noop")
    job.refresh_from_db()

    deleted = JobHandler.cleanup_old_jobs()
    assert deleted == 0
    assert Job.objects.filter(pk=job.pk).exists()

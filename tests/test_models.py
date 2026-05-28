"""
Tests for the Job model: state transitions, Redis cache, .specific proxy.
"""

from __future__ import annotations

import pytest

from task_ferry.models import (
    JOB_CANCELLED,
    JOB_FAILED,
    JOB_FINISHED,
    JOB_PENDING,
    JOB_STARTED,
    Job,
)


@pytest.mark.django_db
def test_job_initial_state(noop_job_type, user):
    job = noop_job_type.model_class.objects.create(
        user=user,
        content_type=_ct(noop_job_type.model_class),
    )
    assert job.state == JOB_PENDING
    assert job.progress_percentage == 0


@pytest.mark.django_db
def test_mark_started(noop_job_type, user):
    job = _make_job(noop_job_type, user)
    job.mark_started()
    job.refresh_from_db()
    assert job.state == JOB_STARTED


@pytest.mark.django_db
def test_mark_finished(noop_job_type, user):
    job = _make_job(noop_job_type, user)
    job.mark_started()
    job.mark_finished()
    job.refresh_from_db()
    assert job.state == JOB_FINISHED
    assert job.progress_percentage == 100
    assert job.has_ended is True


@pytest.mark.django_db
def test_mark_failed(noop_job_type, user):
    job = _make_job(noop_job_type, user)
    job.mark_failed(error="oops", human_readable_error="Something went wrong")
    job.refresh_from_db()
    assert job.state == JOB_FAILED
    assert job.error == "oops"
    assert job.has_ended is True


@pytest.mark.django_db
def test_mark_cancelled(noop_job_type, user):
    job = _make_job(noop_job_type, user)
    job.mark_cancelled()
    job.refresh_from_db()
    assert job.state == JOB_CANCELLED
    assert job.is_cancelled is True
    assert job.has_ended is True


@pytest.mark.django_db
def test_set_progress_updates_cache(noop_job_type, user):
    job = _make_job(noop_job_type, user)
    job.set_progress(42, "halfway")
    # Should be readable from cache without touching DB.
    assert job.get_cached_progress_percentage() == 42


@pytest.mark.django_db
def test_clear_cache(noop_job_type, user):
    job = _make_job(noop_job_type, user)
    job.set_progress(55, "working")
    job.clear_cache()
    # set_progress() only wrote to Redis (not DB), so after clearing the
    # cache and refreshing the instance from DB, the value is back to 0.
    job.refresh_from_db()
    assert job.get_cached_progress_percentage() == 0


@pytest.mark.django_db
def test_get_cached_state_falls_back_to_db(noop_job_type, user):
    job = _make_job(noop_job_type, user)
    # No cache entry yet → should return DB state.
    assert job.get_cached_state() == JOB_PENDING


@pytest.mark.django_db
def test_specific_returns_proxy_instance(noop_job_type, user):
    job = _make_job(noop_job_type, user)
    base_job = Job.objects.get(pk=job.pk)
    specific = base_job.specific
    assert isinstance(specific, noop_job_type.model_class)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ct(model_class):
    from django.contrib.contenttypes.models import ContentType
    # for_concrete_model=False so proxy models get their own CT entry,
    # matching what the handler does — required for .specific to work.
    return ContentType.objects.get_for_model(model_class, for_concrete_model=False)


def _make_job(job_type, user):
    return job_type.model_class.objects.create(
        user=user,
        content_type=_ct(job_type.model_class),
    )

"""
Shared pytest fixtures for django-task-ferry tests.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Cache isolation
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_cache_between_tests():
    """
    Wipe the Django cache before every test.

    LocMemCache is process-global.  Without this, a cancelled job writes
    state=cancelled to the cache; the transaction rolls back so the DB row
    is gone, but the cache entry lingers.  The next test creates a new row
    with the same PK (SQLite in-memory resets sequences) and reads the
    stale entry, producing false 'has_ended' results.
    """
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()


# ---------------------------------------------------------------------------
# User fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def user(db):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.create_user(username="testuser", password="pass")


@pytest.fixture
def other_user(db):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.create_user(username="otheruser", password="pass")


# ---------------------------------------------------------------------------
# Minimal JobType fixture (no-op job for unit tests)
# ---------------------------------------------------------------------------

@pytest.fixture
def noop_job_type(db):
    """
    Register a minimal JobType that does nothing and cleans up after itself.
    """
    from task_ferry.models import Job
    from task_ferry.registry import JobType, job_type_registry

    # Concrete model (plain proxy is enough for testing — no extra fields).
    class NoopJob(Job):
        class Meta:
            app_label = "task_ferry"
            # Use the same DB table as Job (proxy model).
            proxy = True

    class NoopJobType(JobType):
        type = "noop"
        model_class = NoopJob
        max_count = 3

        def run(self, job, progress):
            progress.increment(100, state="done")
            return "ok"

    jt = NoopJobType()
    job_type_registry.register(jt)
    yield jt
    # Cleanup: remove from registry so tests don't bleed into each other.
    job_type_registry._by_type.pop("noop", None)
    job_type_registry._by_model.pop(NoopJob, None)
    # Clear the ContentType in-memory cache.  Without this, after the test
    # transaction rolls back the django_content_type row, a subsequent test
    # may read a stale cached CT id that no longer exists in the DB and
    # trigger an FK integrity error at teardown.
    from django.contrib.contenttypes.models import ContentType
    ContentType.objects.clear_cache()


@pytest.fixture
def failing_job_type(db):
    """JobType whose run() always raises."""
    from task_ferry.models import Job
    from task_ferry.registry import JobType, job_type_registry

    class FailingJob(Job):
        class Meta:
            app_label = "task_ferry"
            proxy = True

    class FailingJobType(JobType):
        type = "failing"
        model_class = FailingJob
        max_count = 5

        def run(self, job, progress):
            raise ValueError("boom")

    jt = FailingJobType()
    job_type_registry.register(jt)
    yield jt
    job_type_registry._by_type.pop("failing", None)
    job_type_registry._by_model.pop(FailingJob, None)
    from django.contrib.contenttypes.models import ContentType
    ContentType.objects.clear_cache()

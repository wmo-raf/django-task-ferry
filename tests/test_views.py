"""
Tests for the DRF API layer: JobListView, JobRetrieveView, JobCancelView.
"""

from __future__ import annotations

import pytest
from django.test import RequestFactory
from rest_framework.test import APIRequestFactory, force_authenticate

from task_ferry.api.views import JobCancelView, JobListView, JobRetrieveView
from task_ferry.handler import JobHandler
from task_ferry.models import JOB_CANCELLED, JOB_FINISHED


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

factory = APIRequestFactory()


def _list(user, params=""):
    request = factory.get(f"/jobs/{params}")
    force_authenticate(request, user=user)
    response = JobListView.as_view()(request)
    response.accepted_renderer = _dummy_renderer()
    response.accepted_media_type = "application/json"
    response.renderer_context = {}
    return response


def _detail(user, job_id):
    request = factory.get(f"/jobs/{job_id}/")
    force_authenticate(request, user=user)
    response = JobRetrieveView.as_view()(request, job_id=job_id)
    return response


def _cancel(user, job_id):
    request = factory.post(f"/jobs/{job_id}/cancel/")
    force_authenticate(request, user=user)
    response = JobCancelView.as_view()(request, job_id=job_id)
    return response


class _dummy_renderer:
    media_type = "application/json"
    format = "json"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        import json
        return json.dumps(data).encode()


# ---------------------------------------------------------------------------
# List view
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_list_returns_users_jobs(noop_job_type, user):
    JobHandler.create_and_start(user, "noop")
    request = factory.get("/jobs/")
    force_authenticate(request, user=user)
    response = JobListView.as_view()(request)
    assert response.status_code == 200
    assert len(response.data) == 1


@pytest.mark.django_db
def test_list_does_not_show_other_users_jobs(noop_job_type, user, other_user):
    JobHandler.create_and_start(user, "noop")
    request = factory.get("/jobs/")
    force_authenticate(request, user=other_user)
    response = JobListView.as_view()(request)
    assert response.status_code == 200
    assert len(response.data) == 0


@pytest.mark.django_db
def test_list_unauthenticated_returns_403(noop_job_type):
    request = factory.get("/jobs/")
    response = JobListView.as_view()(request)
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Detail / polling view
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_detail_returns_job(noop_job_type, user):
    job = JobHandler.create_and_start(user, "noop")
    response = _detail(user, job.id)
    assert response.status_code == 200
    assert response.data["id"] == job.id
    assert response.data["state"] == JOB_FINISHED


@pytest.mark.django_db
def test_detail_wrong_user_returns_404(noop_job_type, user, other_user):
    job = JobHandler.create_and_start(user, "noop")
    response = _detail(other_user, job.id)
    assert response.status_code == 404


@pytest.mark.django_db
def test_detail_missing_job_returns_404(noop_job_type, user):
    response = _detail(user, 99999)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Cancel view
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_cancel_pending_job(noop_job_type, user, monkeypatch):
    from task_ferry.executors.immediate import ImmediateExecutor

    monkeypatch.setattr(ImmediateExecutor, "enqueue", lambda self, job_id: None)

    job = JobHandler.create_and_start(user, "noop")
    response = _cancel(user, job.id)
    assert response.status_code == 200
    assert response.data["state"] == JOB_CANCELLED


@pytest.mark.django_db
def test_cancel_finished_job_returns_400(noop_job_type, user):
    job = JobHandler.create_and_start(user, "noop")
    response = _cancel(user, job.id)
    assert response.status_code == 400


@pytest.mark.django_db
def test_cancel_missing_job_returns_404(noop_job_type, user):
    response = _cancel(user, 99999)
    assert response.status_code == 404

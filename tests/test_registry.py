"""
Tests for JobType and job_type_registry.
"""

from __future__ import annotations

import pytest

from task_ferry.exceptions import JobTypeNotRegistered
from task_ferry.models import Job
from task_ferry.registry import JobType, _JobTypeRegistry


# ---------------------------------------------------------------------------
# Helpers — build isolated registry + type per test so they don't share state
# ---------------------------------------------------------------------------

def _make_registry():
    return _JobTypeRegistry()


def _make_job_type(type_name="demo"):
    class DemoJob(Job):
        class Meta:
            app_label = "task_ferry"
            proxy = True

    class DemoJobType(JobType):
        type = type_name
        model_class = DemoJob

        def run(self, job, progress):
            return "done"

    return DemoJobType()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_register_and_get():
    reg = _make_registry()
    jt = _make_job_type("alpha")
    reg.register(jt)
    assert reg.get("alpha") is jt


def test_get_unknown_raises():
    reg = _make_registry()
    with pytest.raises(JobTypeNotRegistered):
        reg.get("ghost")


def test_get_by_model():
    reg = _make_registry()
    jt = _make_job_type("beta")
    reg.register(jt)

    # get_by_model accepts a Job instance (using its class).
    instance = jt.model_class()
    assert reg.get_by_model(instance) is jt


def test_all_returns_all_types():
    reg = _make_registry()
    jt1 = _make_job_type("x")
    jt2 = _make_job_type("y")
    reg.register(jt1)
    reg.register(jt2)
    assert set(reg.all()) == {jt1, jt2}


def test_duplicate_registration_raises():
    reg = _make_registry()
    jt = _make_job_type("dup")
    reg.register(jt)
    with pytest.raises(Exception):
        reg.register(jt)


def test_job_type_prepare_values_passthrough():
    jt = _make_job_type()
    result = jt.prepare_values({"foo": "bar"}, user=None)
    assert result == {"foo": "bar"}


def test_job_type_hooks_are_no_ops():
    """Default hook implementations should not raise."""
    jt = _make_job_type()
    job = object()  # dummy — hooks shouldn't inspect it
    jt.after_job_creation(job, {})
    jt.on_error(job, ValueError("x"))
    jt.on_cancelled(job)
    jt.before_delete(job)

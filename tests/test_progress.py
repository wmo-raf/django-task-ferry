"""
Tests for the Progress helper: increment, percentage, child progress,
and the updated_event callback chain.
"""

from __future__ import annotations

import pytest

from task_ferry.progress import Progress


def test_initial_percentage():
    p = Progress(total=10)
    assert p.percentage == 0


def test_increment_updates_percentage():
    p = Progress(total=4)
    p.increment(2)
    assert p.percentage == 50


def test_increment_clamps_to_100():
    p = Progress(total=1)
    p.increment(999)
    assert p.percentage == 100


def test_full_increment():
    p = Progress(total=5)
    for _ in range(5):
        p.increment(1)
    assert p.percentage == 100


def test_callback_fires_on_increment():
    calls = []
    p = Progress(total=10)
    p.register_updated_event(lambda pct, label: calls.append((pct, label)))
    p.increment(5, state="halfway")
    assert len(calls) == 1
    assert calls[0] == (50, "halfway")


def test_multiple_callbacks():
    calls_a, calls_b = [], []
    p = Progress(total=2)
    p.register_updated_event(lambda pct, lbl: calls_a.append(pct))
    p.register_updated_event(lambda pct, lbl: calls_b.append(pct))
    p.increment(1)
    assert calls_a == [50]
    assert calls_b == [50]


def test_child_progress_propagates_to_parent():
    parent_calls = []
    parent = Progress(total=2)
    parent.register_updated_event(lambda pct, lbl: parent_calls.append(pct))

    # Child represents 1 out of parent's 2 units (50% of parent).
    child = parent.create_child(represents=1, total=4)
    child.increment(4)  # child finishes → parent advances by 1/2

    assert parent.percentage == 50


def test_child_label_propagates():
    labels = []
    parent = Progress(total=1)
    parent.register_updated_event(lambda pct, lbl: labels.append(lbl))

    child = parent.create_child(represents=1, total=1)
    child.increment(1, state="child done")

    assert labels[-1] == "child done"


def test_multiple_children():
    parent = Progress(total=4)
    c1 = parent.create_child(represents=2, total=2)  # covers 50%
    c2 = parent.create_child(represents=2, total=2)  # covers 50%

    c1.increment(2)
    assert parent.percentage == 50

    c2.increment(2)
    assert parent.percentage == 100


def test_fractional_progress_rounds_down():
    p = Progress(total=3)
    p.increment(1)  # 33.3% → 33
    assert p.percentage == 33

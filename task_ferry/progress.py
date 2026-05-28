"""
Hierarchical progress tracker.

A Progress instance represents a slice of work with a known total number
of steps. Child progress objects can be carved out of a parent, each
owning a sub-range of the parent's percentage. Callbacks fire whenever
progress changes at any level of the hierarchy.

Example — three pipeline stages with unequal weights:

    def on_update(pct, label):
        job.set_progress(pct, label)

    root = Progress(total=100)
    root.register_updated_event(on_update)

    # Stage 1: download (10% of total)
    root.increment(by=10, state="Downloading file...")

    # Stage 2: process variables (70% of total, 5 variables)
    stage2 = root.create_child(represents=70, total=5)
    for i, var in enumerate(variables):
        stage2.increment(state=f"Processing {var.slug}...")

    # Stage 3: archive + cleanup (remaining 20%)
    root.increment(by=20, state="Archiving...")
"""

from __future__ import annotations

from typing import Callable, List, Optional


class Progress:
    def __init__(
        self,
        total: int,
        *,
        parent: Optional[Progress] = None,
        represents: Optional[float] = None,
        start_offset: float = 0.0,
    ) -> None:
        """
        :param total:        How many increments = 100% of this progress object.
        :param parent:       Parent progress that owns a range this child fills.
        :param represents:   How many of the parent's units this child covers.
        :param start_offset: The parent's _progress value at the moment this
                             child was created. Used to correctly advance the
                             parent when multiple children are in play.
        """
        if total <= 0:
            raise ValueError("Progress total must be a positive integer.")

        self.total = total
        self._direct_progress: float = 0.0   # from this object's own increment() calls
        self._progress: float = 0.0          # direct + all child contributions
        self._parent = parent
        self._represents = represents
        self._start_offset = start_offset    # parent progress when child was born
        self._callbacks: List[Callable[[int, str], None]] = []
        # Maps child id → its current contribution to this parent's progress.
        self._child_contribs: dict = {}

    # ── Public API ─────────────────────────────────────────────────────────────

    def register_updated_event(self, fn: Callable[[int, str], None]) -> None:
        """
        Register a callback invoked on every progress change.
        Signature: fn(percentage: int, state_label: str)
        """
        self._callbacks.append(fn)

    def increment(self, by: float = 1.0, state: str = "") -> None:
        """
        Advance progress by *by* steps and fire callbacks.
        Clamped to total — will not exceed 100%.
        """
        remaining = self.total - self._direct_progress - sum(self._child_contribs.values())
        actual = min(by, remaining)
        self._direct_progress += actual
        self._progress = self._direct_progress + sum(self._child_contribs.values())
        self._notify(self.percentage, state)

    def create_child(self, represents: float, total: int) -> Progress:
        """
        Create a child progress object that represents *represents* units
        of this parent's total.

        When the child increments, the parent's percentage advances
        proportionally. Only root-level progress (no parent) fires the
        registered callbacks — children bubble upward.

        :param represents: Parent units consumed when the child completes.
        :param total:      Number of child steps that equal full completion.
        """
        return Progress(
            total=total,
            parent=self,
            represents=represents,
            start_offset=self._progress,
        )

    @property
    def percentage(self) -> int:
        """Current completion as an integer 0–100."""
        return min(100, int(self._progress / self.total * 100))

    # ── Internals ──────────────────────────────────────────────────────────────

    def _notify(self, pct: int, state: str) -> None:
        if self._parent is not None:
            # Bubble progress up to the root — only root fires user callbacks.
            self._parent._child_advanced(self, state)
        else:
            for fn in self._callbacks:
                fn(pct, state)

    def _child_advanced(self, child: Progress, state: str) -> None:
        """
        Called by a child when it advances. Updates this child's contribution
        slot in the parent's contribution map, then recalculates total progress
        and bubbles up.

        Using a per-child contribution dict means multiple children can be
        created up front and advanced independently without overwriting each
        other's progress.
        """
        child_fraction = child._progress / child.total
        self._child_contribs[id(child)] = child_fraction * child._represents  # type: ignore[operator]
        self._progress = self._direct_progress + sum(self._child_contribs.values())
        self._notify(self.percentage, state)

    def __repr__(self) -> str:
        return f"<Progress {self.percentage}% ({self._progress}/{self.total})>"

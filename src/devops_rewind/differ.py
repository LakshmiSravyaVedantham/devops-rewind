"""
Session diff engine for devops-rewind.

Compares two sessions side-by-side and identifies where they diverge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from devops_rewind.session import Session, Step


@dataclass
class StepDiff:
    """Represents the comparison of two steps at the same position."""

    step_index: int
    step_a: Optional[Step]
    step_b: Optional[Step]
    commands_match: bool
    outputs_match: bool
    exit_codes_match: bool

    @property
    def fully_identical(self) -> bool:
        return self.commands_match and self.outputs_match and self.exit_codes_match

    @property
    def is_missing_a(self) -> bool:
        return self.step_a is None

    @property
    def is_missing_b(self) -> bool:
        return self.step_b is None


@dataclass
class DiffResult:
    """Full diff result between two sessions."""

    session_a_id: str
    session_b_id: str
    diffs: List[StepDiff]
    diverge_point: Optional[int]

    @property
    def are_identical(self) -> bool:
        return all(d.fully_identical for d in self.diffs)

    @property
    def changed_steps(self) -> List[StepDiff]:
        return [d for d in self.diffs if not d.fully_identical]


def diff_sessions(
    session_a: Session,
    session_b: Session,
    from_step: int = 0,
) -> DiffResult:
    """
    Compare two sessions step-by-step starting from from_step.

    Finds the divergence point (first step where commands differ) and
    produces a StepDiff for every step in the longer session.

    Args:
        session_a:  First session to compare.
        session_b:  Second session to compare.
        from_step:  Start comparison from this step number.

    Returns:
        DiffResult with per-step diffs and the divergence point.
    """
    max_steps = max(session_a.total_steps, session_b.total_steps)
    diffs: List[StepDiff] = []
    diverge_point: Optional[int] = None

    for i in range(from_step, max_steps):
        step_a = session_a.get_step(i)
        step_b = session_b.get_step(i)

        if step_a is None and step_b is None:
            continue

        commands_match = step_a is not None and step_b is not None and step_a.command == step_b.command
        outputs_match = step_a is not None and step_b is not None and step_a.output == step_b.output
        exit_codes_match = step_a is not None and step_b is not None and step_a.exit_code == step_b.exit_code

        diff = StepDiff(
            step_index=i,
            step_a=step_a,
            step_b=step_b,
            commands_match=commands_match,
            outputs_match=outputs_match,
            exit_codes_match=exit_codes_match,
        )
        diffs.append(diff)

        if diverge_point is None and not commands_match:
            diverge_point = i

    return DiffResult(
        session_a_id=session_a.id,
        session_b_id=session_b.id,
        diffs=diffs,
        diverge_point=diverge_point,
    )


def summarize_diff(result: DiffResult) -> str:
    """Return a short human-readable summary of a DiffResult."""
    if result.are_identical:
        return "Sessions are identical in the compared range."

    lines = []
    if result.diverge_point is not None:
        lines.append(f"Sessions diverge at step {result.diverge_point}.")
    changed = len(result.changed_steps)
    lines.append(f"{changed} step(s) differ.")

    only_in_a = sum(1 for d in result.diffs if d.step_b is None)
    only_in_b = sum(1 for d in result.diffs if d.step_a is None)
    if only_in_a:
        lines.append(f"{only_in_a} step(s) only in session A.")
    if only_in_b:
        lines.append(f"{only_in_b} step(s) only in session B.")

    return "  ".join(lines)

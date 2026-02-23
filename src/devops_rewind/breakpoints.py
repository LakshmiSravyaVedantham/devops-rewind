"""
Breakpoint management for devops-rewind.

Breakpoints can be:
  - Step-based:   trigger at a specific step number
  - Pattern-based: trigger when a command matches a regex
  - Error-based:  trigger on any non-zero exit code
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from devops_rewind.session import Step
from devops_rewind.storage import Storage


@dataclass
class Breakpoint:
    """Represents a single breakpoint condition."""

    id: int
    session_id: str
    step_number: Optional[int] = None
    pattern: Optional[str] = None
    on_error: bool = False

    def matches_step(self, step: Step) -> bool:
        """
        Return True if this breakpoint triggers for the given Step.

        A breakpoint triggers if ANY of its conditions match:
          - step_number matches step.step_number
          - pattern matches step.command (regex)
          - on_error is True and step.exit_code != 0
        """
        if self.step_number is not None and step.step_number == self.step_number:
            return True

        if self.pattern is not None:
            try:
                if re.search(self.pattern, step.command):
                    return True
            except re.error:
                pass

        if self.on_error and step.exit_code != 0:
            return True

        return False

    def describe(self) -> str:
        """Return a human-readable description of the breakpoint."""
        parts = [f"BP#{self.id}"]
        if self.step_number is not None:
            parts.append(f"at step {self.step_number}")
        if self.pattern is not None:
            parts.append(f"on pattern /{self.pattern}/")
        if self.on_error:
            parts.append("on any error")
        return ", ".join(parts)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "step_number": self.step_number,
            "pattern": self.pattern,
            "on_error": self.on_error,
        }


class BreakpointManager:
    """Manages breakpoints for a specific session backed by Storage."""

    def __init__(self, session_id: str, storage: Storage) -> None:
        self.session_id = session_id
        self.storage = storage

    def add(
        self,
        step_number: Optional[int] = None,
        pattern: Optional[str] = None,
        on_error: bool = False,
    ) -> Breakpoint:
        """Add a new breakpoint and return it."""
        if step_number is None and pattern is None and not on_error:
            raise ValueError("At least one of step_number, pattern, or on_error must be set.")

        if pattern is not None:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"Invalid regex pattern: {exc}") from exc

        bp_id = self.storage.add_breakpoint(
            session_id=self.session_id,
            step_number=step_number,
            pattern=pattern,
            on_error=on_error,
        )
        return Breakpoint(
            id=bp_id,
            session_id=self.session_id,
            step_number=step_number,
            pattern=pattern,
            on_error=on_error,
        )

    def remove(self, bp_id: int) -> bool:
        """Remove a breakpoint by ID. Returns True if it was deleted."""
        return self.storage.remove_breakpoint(bp_id)

    def list(self) -> List[Breakpoint]:
        """Return all breakpoints for this session."""
        rows = self.storage.list_breakpoints(self.session_id)
        return [
            Breakpoint(
                id=row["id"],
                session_id=row["session_id"],
                step_number=row["step_number"],
                pattern=row["pattern"],
                on_error=bool(row["on_error"]),
            )
            for row in rows
        ]

    def check(self, step: Step) -> List[Breakpoint]:
        """
        Return all breakpoints that trigger for the given step.

        Call this after each step during replay or recording to detect hits.
        """
        return [bp for bp in self.list() if bp.matches_step(step)]

    def check_step_number(self, step_number: int) -> List[Breakpoint]:
        """Return all step-based breakpoints targeting the given step_number."""
        return [bp for bp in self.list() if bp.step_number == step_number]

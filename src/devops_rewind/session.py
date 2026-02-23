"""
Session data model and management for devops-rewind.

Defines the core Step and Session dataclasses used throughout the system.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


@dataclass
class Step:
    """Represents a single recorded command step in a session."""

    step_number: int
    command: str
    output: str
    exit_code: int
    timestamp: datetime
    cwd: str
    env_snapshot: Dict[str, str] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        """Return True if the command exited with code 0."""
        return self.exit_code == 0

    @property
    def failed(self) -> bool:
        """Return True if the command exited with a non-zero code."""
        return self.exit_code != 0

    def to_dict(self) -> dict:
        """Serialize the step to a dictionary."""
        return {
            "step_number": self.step_number,
            "command": self.command,
            "output": self.output,
            "exit_code": self.exit_code,
            "timestamp": self.timestamp.isoformat(),
            "cwd": self.cwd,
            "env_snapshot": self.env_snapshot,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Step":
        """Deserialize a step from a dictionary."""
        ts_raw = data["timestamp"]
        if isinstance(ts_raw, str):
            from dateutil.parser import parse as parse_dt

            timestamp = parse_dt(ts_raw)
        else:
            timestamp = ts_raw
        return cls(
            step_number=data["step_number"],
            command=data["command"],
            output=data["output"],
            exit_code=data["exit_code"],
            timestamp=timestamp,
            cwd=data["cwd"],
            env_snapshot=data.get("env_snapshot", {}),
        )

    def __repr__(self) -> str:
        status = "OK" if self.succeeded else f"ERR({self.exit_code})"
        return f"Step({self.step_number}: {self.command!r} [{status}])"


@dataclass
class Session:
    """Represents a complete recorded terminal session."""

    id: str
    name: str
    created_at: datetime
    steps: List[Step] = field(default_factory=list)
    parent_id: Optional[str] = None
    fork_step: Optional[int] = None

    @classmethod
    def new(cls, name: str, parent_id: Optional[str] = None, fork_step: Optional[int] = None) -> "Session":
        """Create a new session with a generated UUID."""
        return cls(
            id=str(uuid.uuid4()),
            name=name,
            created_at=datetime.now(timezone.utc),
            steps=[],
            parent_id=parent_id,
            fork_step=fork_step,
        )

    @property
    def total_steps(self) -> int:
        """Return the total number of recorded steps."""
        return len(self.steps)

    @property
    def duration(self) -> Optional[float]:
        """Return the total duration in seconds, or None if fewer than 2 steps."""
        if len(self.steps) < 2:
            return None
        first = self.steps[0].timestamp
        last = self.steps[-1].timestamp
        delta = last - first
        return delta.total_seconds()

    @property
    def is_branch(self) -> bool:
        """Return True if this session was forked from another."""
        return self.parent_id is not None

    def get_step(self, step_number: int) -> Optional[Step]:
        """Return the step with the given step_number, or None."""
        for step in self.steps:
            if step.step_number == step_number:
                return step
        return None

    def get_range(self, from_step: int, to_step: int) -> List[Step]:
        """Return steps from from_step to to_step (inclusive)."""
        return [s for s in self.steps if from_step <= s.step_number <= to_step]

    def add_step(self, step: Step) -> None:
        """Append a step to the session."""
        self.steps.append(step)

    def to_dict(self) -> dict:
        """Serialize the session to a dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "steps": [s.to_dict() for s in self.steps],
            "parent_id": self.parent_id,
            "fork_step": self.fork_step,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        """Deserialize a session from a dictionary."""
        from dateutil.parser import parse as parse_dt

        ts_raw = data["created_at"]
        created_at = parse_dt(ts_raw) if isinstance(ts_raw, str) else ts_raw
        steps = [Step.from_dict(s) for s in data.get("steps", [])]
        return cls(
            id=data["id"],
            name=data["name"],
            created_at=created_at,
            steps=steps,
            parent_id=data.get("parent_id"),
            fork_step=data.get("fork_step"),
        )

    def __repr__(self) -> str:
        return f"Session(id={self.id[:8]}..., name={self.name!r}, steps={self.total_steps})"

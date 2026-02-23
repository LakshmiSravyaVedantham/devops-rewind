"""
Shared pytest fixtures for devops-rewind tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from devops_rewind.session import Session, Step
from devops_rewind.storage import Storage


@pytest.fixture
def tmp_db(tmp_path: Path) -> Storage:
    """Return a Storage instance backed by a temporary SQLite file."""
    db_path = tmp_path / "test.db"
    storage = Storage(db_path=db_path)
    yield storage
    storage.close()


def _make_step(
    step_number: int = 0,
    command: str = "echo hello",
    output: str = "hello",
    exit_code: int = 0,
    cwd: str = "/tmp",
) -> Step:
    return Step(
        step_number=step_number,
        command=command,
        output=output,
        exit_code=exit_code,
        timestamp=datetime(2024, 1, 1, 12, 0, step_number, tzinfo=timezone.utc),
        cwd=cwd,
        env_snapshot={"PATH": "/usr/bin", "HOME": "/home/user"},
    )


@pytest.fixture
def simple_session() -> Session:
    """Return a Session with 5 steps (step 3 fails)."""
    session = Session.new("test-session")
    steps = [
        _make_step(0, "git status", "On branch main", 0),
        _make_step(1, "make build", "Build OK", 0),
        _make_step(2, "make test", "All tests passed", 0),
        _make_step(3, "make deploy", "Error: connection refused", 1),
        _make_step(4, "make rollback", "Rollback complete", 0),
    ]
    for s in steps:
        session.add_step(s)
    return session


@pytest.fixture
def empty_session() -> Session:
    """Return a Session with no steps."""
    return Session.new("empty-session")

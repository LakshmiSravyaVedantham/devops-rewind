"""
Tests for the Session and Step data models.
"""

from __future__ import annotations

from datetime import datetime, timezone

from devops_rewind.session import Session, Step


class TestStep:
    def test_step_succeeded(self):
        step = Step(0, "echo ok", "ok", 0, datetime.now(timezone.utc), "/tmp")
        assert step.succeeded is True
        assert step.failed is False

    def test_step_failed(self):
        step = Step(1, "false", "", 1, datetime.now(timezone.utc), "/tmp")
        assert step.succeeded is False
        assert step.failed is True

    def test_step_to_dict_round_trip(self):
        ts = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        step = Step(
            step_number=5,
            command="ls -la",
            output="total 0",
            exit_code=0,
            timestamp=ts,
            cwd="/home/user",
            env_snapshot={"PATH": "/usr/bin"},
        )
        d = step.to_dict()
        assert d["step_number"] == 5
        assert d["command"] == "ls -la"

        reconstructed = Step.from_dict(d)
        assert reconstructed.step_number == 5
        assert reconstructed.command == "ls -la"
        assert reconstructed.output == "total 0"
        assert reconstructed.exit_code == 0
        assert reconstructed.cwd == "/home/user"
        assert reconstructed.env_snapshot == {"PATH": "/usr/bin"}

    def test_step_repr(self):
        step = Step(3, "make deploy", "Error", 1, datetime.now(timezone.utc), "/app")
        r = repr(step)
        assert "3" in r
        assert "make deploy" in r
        assert "ERR" in r


class TestSession:
    def test_session_new_generates_id(self):
        s = Session.new("my-session")
        assert len(s.id) == 36  # UUID4
        assert s.name == "my-session"
        assert s.total_steps == 0
        assert s.is_branch is False

    def test_add_step(self):
        session = Session.new("s")
        step = Step(0, "pwd", "/tmp", 0, datetime.now(timezone.utc), "/tmp")
        session.add_step(step)
        assert session.total_steps == 1

    def test_get_step_found(self, simple_session):
        step = simple_session.get_step(2)
        assert step is not None
        assert step.command == "make test"

    def test_get_step_not_found(self, simple_session):
        assert simple_session.get_step(99) is None

    def test_get_range(self, simple_session):
        steps = simple_session.get_range(1, 3)
        assert len(steps) == 3
        assert steps[0].step_number == 1
        assert steps[-1].step_number == 3

    def test_duration(self, simple_session):
        dur = simple_session.duration
        assert dur is not None
        assert dur >= 0

    def test_duration_empty(self, empty_session):
        assert empty_session.duration is None

    def test_session_round_trip(self, simple_session):
        d = simple_session.to_dict()
        restored = Session.from_dict(d)
        assert restored.id == simple_session.id
        assert restored.name == simple_session.name
        assert restored.total_steps == simple_session.total_steps
        assert restored.steps[3].exit_code == 1

    def test_branch_flag(self):
        parent = Session.new("parent")
        child = Session.new("child", parent_id=parent.id, fork_step=2)
        assert child.is_branch is True
        assert child.parent_id == parent.id
        assert child.fork_step == 2

    def test_session_repr(self, simple_session):
        r = repr(simple_session)
        assert "test-session" in r
        assert "5" in r

"""
Tests for the session diff engine.
"""

from __future__ import annotations

from datetime import datetime, timezone

from devops_rewind.differ import diff_sessions, summarize_diff
from devops_rewind.session import Session, Step


def _make_step(n, cmd, out="", code=0):
    return Step(n, cmd, out, code, datetime.now(timezone.utc), "/tmp")


def _session_with_steps(name, commands):
    s = Session.new(name)
    for i, cmd in enumerate(commands):
        s.add_step(_make_step(i, cmd))
    return s


class TestDiffSessions:
    def test_identical_sessions(self):
        cmds = ["git pull", "make build", "make test"]
        a = _session_with_steps("a", cmds)
        b = _session_with_steps("b", cmds)
        result = diff_sessions(a, b)
        assert result.are_identical is True
        assert result.diverge_point is None

    def test_diverge_at_first_step(self):
        a = _session_with_steps("a", ["git pull", "make build"])
        b = _session_with_steps("b", ["git fetch", "make build"])
        result = diff_sessions(a, b)
        assert result.diverge_point == 0
        assert result.are_identical is False

    def test_diverge_midway(self):
        a = _session_with_steps("a", ["git pull", "make build", "make deploy"])
        b = _session_with_steps("b", ["git pull", "make build", "make deploy-staging"])
        result = diff_sessions(a, b)
        assert result.diverge_point == 2

    def test_session_b_longer(self):
        a = _session_with_steps("a", ["cmd1", "cmd2"])
        b = _session_with_steps("b", ["cmd1", "cmd2", "cmd3", "cmd4"])
        result = diff_sessions(a, b)
        # Sessions match for first 2 steps, B has extra steps
        # Steps 2 and 3 are in B but not A
        missing_in_a = [d for d in result.diffs if d.step_a is None]
        assert len(missing_in_a) == 2

    def test_session_a_longer(self):
        a = _session_with_steps("a", ["cmd1", "cmd2", "cmd3"])
        b = _session_with_steps("b", ["cmd1", "cmd2"])
        result = diff_sessions(a, b)
        missing_in_b = [d for d in result.diffs if d.step_b is None]
        assert len(missing_in_b) == 1

    def test_from_step_offset(self):
        a = _session_with_steps("a", ["a", "b", "c", "d"])
        b = _session_with_steps("b", ["X", "b", "c", "d"])
        # Without offset, should diverge at step 0
        r1 = diff_sessions(a, b, from_step=0)
        assert r1.diverge_point == 0
        # With offset=1, the first differing pair is skipped
        r2 = diff_sessions(a, b, from_step=1)
        assert r2.diverge_point is None  # b,c,d are identical

    def test_diff_result_ids(self, simple_session):
        a = simple_session
        b = Session.new("copy")
        for step in a.steps:
            import copy

            b.add_step(copy.deepcopy(step))
        result = diff_sessions(a, b)
        assert result.session_a_id == a.id
        assert result.session_b_id == b.id

    def test_empty_sessions(self):
        a = Session.new("empty-a")
        b = Session.new("empty-b")
        result = diff_sessions(a, b)
        assert result.are_identical is True
        assert len(result.diffs) == 0


class TestSummarizeDiff:
    def test_identical_summary(self):
        cmds = ["step1", "step2"]
        a = _session_with_steps("a", cmds)
        b = _session_with_steps("b", cmds)
        summary = summarize_diff(diff_sessions(a, b))
        assert "identical" in summary.lower()

    def test_diverge_summary(self):
        a = _session_with_steps("a", ["x", "y"])
        b = _session_with_steps("b", ["x", "z"])
        summary = summarize_diff(diff_sessions(a, b))
        assert "diverge" in summary.lower()
        assert "1" in summary

"""
Tests for breakpoint management.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from devops_rewind.breakpoints import Breakpoint, BreakpointManager
from devops_rewind.session import Step


def _step(step_number=0, command="echo ok", exit_code=0):
    return Step(step_number, command, "output", exit_code, datetime.now(timezone.utc), "/tmp")


class TestBreakpointMatching:
    def test_step_number_match(self):
        bp = Breakpoint(id=1, session_id="s", step_number=3)
        assert bp.matches_step(_step(step_number=3)) is True
        assert bp.matches_step(_step(step_number=4)) is False

    def test_pattern_match(self):
        bp = Breakpoint(id=2, session_id="s", pattern=r"make\s+deploy")
        assert bp.matches_step(_step(command="make deploy")) is True
        assert bp.matches_step(_step(command="make build")) is False

    def test_pattern_regex_partial(self):
        bp = Breakpoint(id=3, session_id="s", pattern="deploy")
        assert bp.matches_step(_step(command="./deploy.sh --env prod")) is True

    def test_on_error_match(self):
        bp = Breakpoint(id=4, session_id="s", on_error=True)
        assert bp.matches_step(_step(exit_code=1)) is True
        assert bp.matches_step(_step(exit_code=0)) is False

    def test_no_match(self):
        bp = Breakpoint(id=5, session_id="s", step_number=7)
        assert bp.matches_step(_step(step_number=0)) is False

    def test_multiple_conditions_any_triggers(self):
        bp = Breakpoint(id=6, session_id="s", step_number=5, on_error=True)
        # Matches because on_error is True and exit_code != 0
        assert bp.matches_step(_step(step_number=0, exit_code=1)) is True
        # Also matches because step_number == 5
        assert bp.matches_step(_step(step_number=5, exit_code=0)) is True

    def test_invalid_pattern_no_crash(self):
        bp = Breakpoint(id=7, session_id="s", pattern="[invalid")
        # Should not raise, just not match
        assert bp.matches_step(_step(command="[invalid")) is False

    def test_describe(self):
        bp = Breakpoint(id=1, session_id="s", step_number=3, pattern="fail", on_error=True)
        desc = bp.describe()
        assert "BP#1" in desc
        assert "step 3" in desc
        assert "fail" in desc
        assert "error" in desc


class TestBreakpointManager:
    def test_add_step_breakpoint(self, tmp_db, simple_session):
        tmp_db.save_session(simple_session)
        mgr = BreakpointManager(session_id=simple_session.id, storage=tmp_db)
        bp = mgr.add(step_number=3)
        assert bp.id is not None
        assert bp.step_number == 3

    def test_add_pattern_breakpoint(self, tmp_db, simple_session):
        tmp_db.save_session(simple_session)
        mgr = BreakpointManager(session_id=simple_session.id, storage=tmp_db)
        bp = mgr.add(pattern="deploy")
        assert bp.pattern == "deploy"

    def test_add_on_error_breakpoint(self, tmp_db, simple_session):
        tmp_db.save_session(simple_session)
        mgr = BreakpointManager(session_id=simple_session.id, storage=tmp_db)
        bp = mgr.add(on_error=True)
        assert bp.on_error is True

    def test_add_requires_at_least_one_condition(self, tmp_db, simple_session):
        tmp_db.save_session(simple_session)
        mgr = BreakpointManager(session_id=simple_session.id, storage=tmp_db)
        with pytest.raises(ValueError, match="At least one"):
            mgr.add()

    def test_add_invalid_regex_raises(self, tmp_db, simple_session):
        tmp_db.save_session(simple_session)
        mgr = BreakpointManager(session_id=simple_session.id, storage=tmp_db)
        with pytest.raises(ValueError, match="Invalid regex"):
            mgr.add(pattern="[bad")

    def test_list_breakpoints(self, tmp_db, simple_session):
        tmp_db.save_session(simple_session)
        mgr = BreakpointManager(session_id=simple_session.id, storage=tmp_db)
        mgr.add(step_number=1)
        mgr.add(step_number=3)
        bps = mgr.list()
        assert len(bps) == 2

    def test_remove_breakpoint(self, tmp_db, simple_session):
        tmp_db.save_session(simple_session)
        mgr = BreakpointManager(session_id=simple_session.id, storage=tmp_db)
        bp = mgr.add(step_number=2)
        assert mgr.remove(bp.id) is True
        assert mgr.list() == []

    def test_check_triggered(self, tmp_db, simple_session):
        tmp_db.save_session(simple_session)
        mgr = BreakpointManager(session_id=simple_session.id, storage=tmp_db)
        mgr.add(step_number=3)
        hits = mgr.check(_step(step_number=3))
        assert len(hits) == 1

    def test_check_not_triggered(self, tmp_db, simple_session):
        tmp_db.save_session(simple_session)
        mgr = BreakpointManager(session_id=simple_session.id, storage=tmp_db)
        mgr.add(step_number=3)
        hits = mgr.check(_step(step_number=0))
        assert len(hits) == 0

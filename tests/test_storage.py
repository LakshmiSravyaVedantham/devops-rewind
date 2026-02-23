"""
Tests for the Storage layer (SQLite CRUD).
"""

from __future__ import annotations

from devops_rewind.session import Session


class TestStorage:
    def test_save_and_load_session(self, tmp_db, simple_session):
        tmp_db.save_session(simple_session)
        loaded = tmp_db.load_session(simple_session.id)
        assert loaded is not None
        assert loaded.id == simple_session.id
        assert loaded.name == simple_session.name
        assert loaded.total_steps == 5

    def test_load_nonexistent_returns_none(self, tmp_db):
        assert tmp_db.load_session("nonexistent-id") is None

    def test_list_sessions(self, tmp_db):
        s1 = Session.new("alpha")
        s2 = Session.new("beta")
        tmp_db.save_session(s1)
        tmp_db.save_session(s2)
        sessions = tmp_db.list_sessions()
        ids = [s.id for s in sessions]
        assert s1.id in ids
        assert s2.id in ids

    def test_list_sessions_limit(self, tmp_db):
        for i in range(5):
            tmp_db.save_session(Session.new(f"session-{i}"))
        results = tmp_db.list_sessions(limit=3)
        assert len(results) == 3

    def test_delete_session(self, tmp_db, simple_session):
        tmp_db.save_session(simple_session)
        deleted = tmp_db.delete_session(simple_session.id)
        assert deleted is True
        assert tmp_db.load_session(simple_session.id) is None

    def test_delete_nonexistent(self, tmp_db):
        assert tmp_db.delete_session("ghost-id") is False

    def test_session_exists(self, tmp_db, simple_session):
        tmp_db.save_session(simple_session)
        assert tmp_db.session_exists(simple_session.id) is True
        assert tmp_db.session_exists("nope") is False

    def test_find_by_name(self, tmp_db, simple_session):
        tmp_db.save_session(simple_session)
        found = tmp_db.find_session_by_name("test-session")
        assert found is not None
        assert found.id == simple_session.id

    def test_find_by_name_missing(self, tmp_db):
        assert tmp_db.find_session_by_name("does-not-exist") is None

    def test_steps_cascade_delete(self, tmp_db, simple_session):
        tmp_db.save_session(simple_session)
        tmp_db.delete_session(simple_session.id)
        # After delete, loading returns None (cascade deleted steps)
        assert tmp_db.load_session(simple_session.id) is None

    def test_save_branch_session(self, tmp_db, simple_session):
        tmp_db.save_session(simple_session)
        child = Session.new("child", parent_id=simple_session.id, fork_step=2)
        tmp_db.save_session(child)
        loaded = tmp_db.load_session(child.id)
        assert loaded.parent_id == simple_session.id
        assert loaded.fork_step == 2

    def test_breakpoint_crud(self, tmp_db, simple_session):
        tmp_db.save_session(simple_session)
        bp_id = tmp_db.add_breakpoint(simple_session.id, step_number=3, pattern=None, on_error=False)
        assert isinstance(bp_id, int)

        bps = tmp_db.list_breakpoints(simple_session.id)
        assert len(bps) == 1
        assert bps[0]["step_number"] == 3

        removed = tmp_db.remove_breakpoint(bp_id)
        assert removed is True
        assert tmp_db.list_breakpoints(simple_session.id) == []

"""
Tests for session branching (forking).
"""

from __future__ import annotations

import pytest

from devops_rewind.branching import branch_session, get_branch_lineage


class TestBranchSession:
    def test_branch_creates_new_id(self, simple_session):
        branch = branch_session(simple_session, from_step=2)
        assert branch.id != simple_session.id

    def test_branch_sets_parent(self, simple_session):
        branch = branch_session(simple_session, from_step=2)
        assert branch.parent_id == simple_session.id
        assert branch.fork_step == 2

    def test_branch_copies_steps_up_to_fork(self, simple_session):
        branch = branch_session(simple_session, from_step=2)
        # Should have steps 0, 1, 2 — that is 3 steps
        assert branch.total_steps == 3
        assert branch.steps[0].command == simple_session.steps[0].command
        assert branch.steps[2].command == simple_session.steps[2].command

    def test_branch_from_first_step(self, simple_session):
        branch = branch_session(simple_session, from_step=0)
        assert branch.total_steps == 1
        assert branch.steps[0].command == simple_session.steps[0].command

    def test_branch_from_last_step(self, simple_session):
        last = simple_session.total_steps - 1
        branch = branch_session(simple_session, from_step=last)
        assert branch.total_steps == simple_session.total_steps

    def test_branch_default_name(self, simple_session):
        branch = branch_session(simple_session, from_step=2)
        assert "branch" in branch.name
        assert "2" in branch.name

    def test_branch_custom_name(self, simple_session):
        branch = branch_session(simple_session, from_step=1, new_name="my-branch")
        assert branch.name == "my-branch"

    def test_branch_does_not_mutate_original(self, simple_session):
        original_count = simple_session.total_steps
        branch = branch_session(simple_session, from_step=2)
        # Mutate branch steps
        branch.steps[0].command = "MUTATED"
        # Original should be unchanged
        assert simple_session.steps[0].command != "MUTATED"
        assert simple_session.total_steps == original_count

    def test_branch_empty_session_raises(self, empty_session):
        with pytest.raises(ValueError, match="empty"):
            branch_session(empty_session, from_step=0)

    def test_branch_out_of_range_raises(self, simple_session):
        with pytest.raises(ValueError, match="out of range"):
            branch_session(simple_session, from_step=99)

    def test_branch_negative_step_raises(self, simple_session):
        with pytest.raises(ValueError, match="out of range"):
            branch_session(simple_session, from_step=-1)

    def test_branch_persists_to_storage(self, simple_session, tmp_db):
        tmp_db.save_session(simple_session)
        branch = branch_session(simple_session, from_step=2, storage=tmp_db)
        loaded = tmp_db.load_session(branch.id)
        assert loaded is not None
        assert loaded.parent_id == simple_session.id


class TestGetBranchLineage:
    def test_single_session_lineage(self, simple_session, tmp_db):
        tmp_db.save_session(simple_session)
        chain = get_branch_lineage(simple_session, tmp_db)
        assert len(chain) == 1
        assert chain[0].id == simple_session.id

    def test_two_level_lineage(self, simple_session, tmp_db):
        tmp_db.save_session(simple_session)
        branch = branch_session(simple_session, from_step=2, storage=tmp_db)
        chain = get_branch_lineage(branch, tmp_db)
        assert len(chain) == 2
        assert chain[0].id == simple_session.id
        assert chain[1].id == branch.id

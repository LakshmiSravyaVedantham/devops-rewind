"""
Tests for the Click CLI commands.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from devops_rewind.cli import main
from devops_rewind.session import Session


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def patched_storage(tmp_db):
    """Patch _get_storage to return the tmp_db fixture."""
    with patch("devops_rewind.cli._get_storage", return_value=tmp_db):
        yield tmp_db


class TestVersionCommand:
    def test_version_output(self, runner):
        result = runner.invoke(main, ["version"])
        assert result.exit_code == 0
        assert "devops-rewind" in result.output

    def test_version_flag(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


class TestListCommand:
    def test_list_empty(self, runner, patched_storage):
        result = runner.invoke(main, ["list"])
        assert result.exit_code == 0
        assert "no sessions" in result.output.lower()

    def test_list_with_sessions(self, runner, patched_storage, simple_session):
        patched_storage.save_session(simple_session)
        result = runner.invoke(main, ["list"])
        assert result.exit_code == 0
        # Rich may truncate the name in narrow terminals; check for prefix
        assert "test-s" in result.output

    def test_list_json_format(self, runner, patched_storage, simple_session):
        patched_storage.save_session(simple_session)
        result = runner.invoke(main, ["list", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert data[0]["name"] == "test-session"

    def test_list_limit(self, runner, patched_storage):
        for i in range(5):
            s = Session.new(f"s{i}")
            patched_storage.save_session(s)
        result = runner.invoke(main, ["list", "--limit", "3"])
        assert result.exit_code == 0


class TestReplayCommand:
    def test_replay_by_name(self, runner, patched_storage, simple_session):
        patched_storage.save_session(simple_session)
        result = runner.invoke(main, ["replay", "test-session", "--speed", "999"])
        assert result.exit_code == 0
        assert "git status" in result.output

    def test_replay_nonexistent(self, runner, patched_storage):
        result = runner.invoke(main, ["replay", "ghost-session"])
        assert result.exit_code == 1

    def test_replay_from_to(self, runner, patched_storage, simple_session):
        patched_storage.save_session(simple_session)
        result = runner.invoke(main, ["replay", "test-session", "--from", "2", "--to", "3", "--speed", "999"])
        assert result.exit_code == 0
        assert "make test" in result.output
        assert "git status" not in result.output


class TestRewindCommand:
    def test_rewind_valid_step(self, runner, patched_storage, simple_session):
        patched_storage.save_session(simple_session)
        result = runner.invoke(main, ["rewind", "test-session", "2"])
        assert result.exit_code == 0
        assert "make test" in result.output
        assert "State at step 2" in result.output

    def test_rewind_invalid_step(self, runner, patched_storage, simple_session):
        patched_storage.save_session(simple_session)
        result = runner.invoke(main, ["rewind", "test-session", "99"])
        assert result.exit_code == 0  # Shows error message but doesn't crash
        assert "does not exist" in result.output.lower()


class TestBreakpointCommands:
    def test_bp_add_by_step(self, runner, patched_storage, simple_session):
        patched_storage.save_session(simple_session)
        result = runner.invoke(main, ["breakpoint", "add", "test-session", "3"])
        assert result.exit_code == 0
        assert "added" in result.output.lower()

    def test_bp_add_on_error(self, runner, patched_storage, simple_session):
        patched_storage.save_session(simple_session)
        result = runner.invoke(main, ["breakpoint", "add", "test-session", "--on-error"])
        assert result.exit_code == 0

    def test_bp_list(self, runner, patched_storage, simple_session):
        patched_storage.save_session(simple_session)
        patched_storage.add_breakpoint(simple_session.id, step_number=3, pattern=None, on_error=False)
        result = runner.invoke(main, ["breakpoint", "list", "test-session"])
        assert result.exit_code == 0
        assert "3" in result.output

    def test_bp_list_empty(self, runner, patched_storage, simple_session):
        patched_storage.save_session(simple_session)
        result = runner.invoke(main, ["breakpoint", "list", "test-session"])
        assert result.exit_code == 0
        assert "no breakpoints" in result.output.lower()

    def test_bp_remove(self, runner, patched_storage, simple_session):
        patched_storage.save_session(simple_session)
        bp_id = patched_storage.add_breakpoint(simple_session.id, step_number=2, pattern=None, on_error=False)
        result = runner.invoke(main, ["breakpoint", "remove", "test-session", str(bp_id)])
        assert result.exit_code == 0
        assert "removed" in result.output.lower()


class TestBranchCommand:
    def test_branch_creates_new_session(self, runner, patched_storage, simple_session):
        patched_storage.save_session(simple_session)
        result = runner.invoke(main, ["branch", "test-session", "2"])
        assert result.exit_code == 0
        assert "branch created" in result.output.lower()
        # Should now have 2 sessions
        sessions = patched_storage.list_sessions()
        assert len(sessions) == 2

    def test_branch_out_of_range(self, runner, patched_storage, simple_session):
        patched_storage.save_session(simple_session)
        result = runner.invoke(main, ["branch", "test-session", "99"])
        assert result.exit_code == 1


class TestDiffCommand:
    def test_diff_two_sessions(self, runner, patched_storage, simple_session):
        patched_storage.save_session(simple_session)
        from devops_rewind.branching import branch_session as do_branch

        branch = do_branch(simple_session, from_step=2, storage=patched_storage)
        result = runner.invoke(main, ["diff", "test-session", branch.name])
        assert result.exit_code == 0


class TestDeleteCommand:
    def test_delete_session(self, runner, patched_storage, simple_session):
        patched_storage.save_session(simple_session)
        result = runner.invoke(main, ["delete", "test-session"], input="y\n")
        assert result.exit_code == 0
        assert "deleted" in result.output.lower()
        assert patched_storage.load_session(simple_session.id) is None

    def test_delete_aborted(self, runner, patched_storage, simple_session):
        patched_storage.save_session(simple_session)
        result = runner.invoke(main, ["delete", "test-session"], input="n\n")
        assert result.exit_code != 0 or "aborted" in result.output.lower()
        # Session should still exist
        assert patched_storage.load_session(simple_session.id) is not None


class TestExportCommand:
    def test_export_sh(self, runner, patched_storage, simple_session):
        patched_storage.save_session(simple_session)
        result = runner.invoke(main, ["export", "test-session", "--format", "sh"])
        assert result.exit_code == 0
        assert "#!/usr/bin/env bash" in result.output
        assert "git status" in result.output

    def test_export_json(self, runner, patched_storage, simple_session):
        patched_storage.save_session(simple_session)
        result = runner.invoke(main, ["export", "test-session", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "test-session"
        assert len(data["steps"]) == 5

    def test_export_markdown(self, runner, patched_storage, simple_session):
        patched_storage.save_session(simple_session)
        result = runner.invoke(main, ["export", "test-session", "--format", "markdown"])
        assert result.exit_code == 0
        assert "# Session:" in result.output
        assert "git status" in result.output

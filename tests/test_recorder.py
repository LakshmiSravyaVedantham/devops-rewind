"""
Tests for the SessionRecorder.
"""

from __future__ import annotations

from devops_rewind.recorder import SessionRecorder, _capture_env


class TestCaptureEnv:
    def test_returns_dict(self):
        env = _capture_env()
        assert isinstance(env, dict)

    def test_no_secrets(self):
        env = _capture_env()
        # Should not contain arbitrary env vars
        sensitive_keys = {"AWS_SECRET_ACCESS_KEY", "DATABASE_URL", "PRIVATE_KEY"}
        assert not sensitive_keys.intersection(env.keys())


class TestSessionRecorder:
    def test_record_single_success(self, empty_session):
        recorder = SessionRecorder(session=empty_session)
        step = recorder.record_single("echo hello")
        assert step.command == "echo hello"
        assert step.exit_code == 0
        assert "hello" in step.output
        assert empty_session.total_steps == 1

    def test_record_single_failure(self, empty_session):
        recorder = SessionRecorder(session=empty_session)
        step = recorder.record_single("exit 42")
        assert step.exit_code == 42
        assert empty_session.total_steps == 1

    def test_record_single_cd_valid(self, empty_session, tmp_path):
        recorder = SessionRecorder(session=empty_session)
        step = recorder.record_single(f"cd {tmp_path}")
        assert step.exit_code == 0
        assert recorder.cwd == str(tmp_path)

    def test_record_single_cd_invalid(self, empty_session):
        recorder = SessionRecorder(session=empty_session)
        step = recorder.record_single("cd /nonexistent/path/xyz")
        assert step.exit_code == 1
        assert "no such" in step.output.lower()

    def test_record_single_increments_steps(self, empty_session):
        recorder = SessionRecorder(session=empty_session)
        recorder.record_single("echo 1")
        recorder.record_single("echo 2")
        recorder.record_single("echo 3")
        assert empty_session.total_steps == 3

    def test_record_single_captures_cwd(self, empty_session):
        recorder = SessionRecorder(session=empty_session)
        step = recorder.record_single("pwd")
        assert step.cwd == recorder.cwd

    def test_on_step_callback(self, empty_session):
        collected = []
        recorder = SessionRecorder(session=empty_session, on_step=collected.append)
        recorder.record_single("echo callback-test")
        assert len(collected) == 1
        assert collected[0].command == "echo callback-test"

    def test_record_single_with_storage(self, empty_session, tmp_db):
        recorder = SessionRecorder(session=empty_session, storage=tmp_db)
        recorder.record_single("echo stored")
        loaded = tmp_db.load_session(empty_session.id)
        assert loaded is not None
        assert loaded.total_steps == 1

    def test_step_number_increments(self, empty_session):
        recorder = SessionRecorder(session=empty_session)
        step0 = recorder.record_single("echo zero")
        step1 = recorder.record_single("echo one")
        assert step0.step_number == 0
        assert step1.step_number == 1

    def test_env_snapshot_in_step(self, empty_session):
        recorder = SessionRecorder(session=empty_session)
        step = recorder.record_single("echo env-test")
        assert isinstance(step.env_snapshot, dict)

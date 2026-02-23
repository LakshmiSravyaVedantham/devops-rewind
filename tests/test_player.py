"""
Tests for the SessionPlayer (replay/rewind engine).
"""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from devops_rewind.player import SessionPlayer, _compute_delays


def _player_with_capture() -> tuple:
    """Return (player, console) with captured output."""
    buf = StringIO()
    con = Console(file=buf, width=120, highlight=False, markup=True)
    player = SessionPlayer(console=con)
    return player, buf


class TestComputeDelays:
    def test_single_step_returns_zero(self, simple_session):
        steps = simple_session.get_range(0, 0)
        delays = _compute_delays(steps, speed=1.0)
        assert delays == [0.0]

    def test_delays_length_matches_steps(self, simple_session):
        steps = simple_session.steps
        delays = _compute_delays(steps, speed=1.0)
        assert len(delays) == len(steps)

    def test_first_delay_is_zero(self, simple_session):
        delays = _compute_delays(simple_session.steps, speed=1.0)
        assert delays[0] == 0.0

    def test_speed_multiplier(self, simple_session):
        delays_1x = _compute_delays(simple_session.steps, speed=1.0)
        delays_2x = _compute_delays(simple_session.steps, speed=2.0)
        # 2x speed should produce shorter or equal delays
        for d1, d2 in zip(delays_1x, delays_2x):
            assert d2 <= d1 + 0.001


class TestSessionPlayer:
    def test_replay_empty_session(self, empty_session):
        player, buf = _player_with_capture()
        player.replay(empty_session)
        assert "no steps" in buf.getvalue().lower()

    def test_replay_full_session(self, simple_session):
        player, buf = _player_with_capture()
        player.replay(simple_session, speed=999.0)
        output = buf.getvalue()
        assert "git status" in output
        assert "make deploy" in output

    def test_replay_range(self, simple_session):
        player, buf = _player_with_capture()
        player.replay(simple_session, speed=999.0, from_step=2, to_step=3)
        output = buf.getvalue()
        assert "make test" in output
        assert "make deploy" in output
        # Step 0 and 1 should not appear
        assert "git status" not in output

    def test_replay_invalid_range(self, simple_session):
        player, buf = _player_with_capture()
        player.replay(simple_session, from_step=50, to_step=60)
        assert "no steps" in buf.getvalue().lower()

    def test_rewind_shows_state(self, simple_session):
        player, buf = _player_with_capture()
        player.rewind(simple_session, step=2)
        output = buf.getvalue()
        assert "make test" in output
        assert "State at step 2" in output

    def test_rewind_out_of_range(self, simple_session):
        player, buf = _player_with_capture()
        player.rewind(simple_session, step=99)
        output = buf.getvalue()
        assert "does not exist" in output.lower()

    def test_rewind_empty_session(self, empty_session):
        player, buf = _player_with_capture()
        player.rewind(empty_session, step=0)
        assert "no steps" in buf.getvalue().lower()

    def test_show_step(self, simple_session):
        player, buf = _player_with_capture()
        player.show_step(simple_session, 3)
        assert "make deploy" in buf.getvalue()

    def test_show_step_missing(self, simple_session):
        player, buf = _player_with_capture()
        player.show_step(simple_session, 99)
        assert "not found" in buf.getvalue().lower()

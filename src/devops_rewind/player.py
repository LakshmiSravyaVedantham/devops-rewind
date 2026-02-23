"""
Replay and rewind engine for devops-rewind sessions.
"""

from __future__ import annotations

import time
from typing import Optional

from rich.console import Console
from rich.panel import Panel

from devops_rewind.display import render_session_info, render_step
from devops_rewind.session import Session


class SessionPlayer:
    """Replays and rewinds recorded sessions in the terminal."""

    def __init__(self, console: Optional[Console] = None) -> None:
        self._console = console or Console()

    def replay(
        self,
        session: Session,
        speed: float = 1.0,
        step_mode: bool = False,
        from_step: int = 0,
        to_step: Optional[int] = None,
    ) -> None:
        """
        Replay a session from from_step to to_step.

        Args:
            session:    The session to replay.
            speed:      Playback speed multiplier (1.0 = realtime, 2.0 = 2x faster).
            step_mode:  If True, wait for Enter key between steps.
            from_step:  Step number to start from (inclusive).
            to_step:    Step number to stop at (inclusive). Defaults to last step.
        """
        if session.total_steps == 0:
            self._console.print("[yellow]Session has no steps to replay.[/yellow]")
            return

        effective_to = to_step if to_step is not None else (session.total_steps - 1)
        steps_to_play = session.get_range(from_step, effective_to)

        if not steps_to_play:
            self._console.print(f"[yellow]No steps in range [{from_step}, {effective_to}].[/yellow]")
            return

        self._console.print(render_session_info(session))
        self._console.print(
            f"\n[bold]Replaying steps {from_step}–{effective_to} "
            f"({len(steps_to_play)} steps, speed={speed}x)[/bold]\n"
        )

        # Compute inter-step delays from original timestamps
        delays = _compute_delays(steps_to_play, speed)

        for idx, step in enumerate(steps_to_play):
            self._console.print(render_step(step, show_output=True))

            if step_mode:
                try:
                    input("[dim]  Press Enter for next step…[/dim]")
                except EOFError:
                    break
            else:
                delay = delays[idx]
                if delay > 0:
                    time.sleep(delay)

        self._console.print("\n[bold green]Replay complete.[/bold green]")

    def rewind(self, session: Session, step: int) -> None:
        """
        Display the session state at a given step.

        Shows all steps up to (and including) the target step, highlighting
        the target. Useful for inspecting the state at a past point.

        Args:
            session:  The session to inspect.
            step:     The step number to rewind to.
        """
        if session.total_steps == 0:
            self._console.print("[yellow]Session has no steps.[/yellow]")
            return

        max_step = session.total_steps - 1
        if step > max_step:
            self._console.print(
                f"[red]Step {step} does not exist. Session has {session.total_steps} steps (0–{max_step}).[/red]"
            )
            return

        self._console.print(render_session_info(session))
        self._console.print(
            Panel(
                f"[bold yellow]Rewound to step {step}[/bold yellow]  " f"[dim](showing all steps 0–{step})[/dim]",
                border_style="yellow",
            )
        )

        prior_steps = session.get_range(0, step - 1)
        target_step = session.get_step(step)

        for s in prior_steps:
            self._console.print(render_step(s, show_output=False))

        if target_step is not None:
            self._console.print("\n[bold yellow]>>> TARGET STEP <<<[/bold yellow]")
            self._console.print(render_step(target_step, show_output=True))

        # Summary of state at this point
        failed_prior = sum(1 for s in prior_steps if s.failed)
        cwd = target_step.cwd if target_step else "unknown"
        failures_str = "[red]" + str(failed_prior) + "[/red]" if failed_prior else "[green]0[/green]"
        self._console.print(
            Panel(
                f"[bold]State at step {step}[/bold]\n"
                f"  Working directory: [cyan]{cwd}[/cyan]\n"
                f"  Steps executed:    {step + 1}\n"
                f"  Prior failures:    {failures_str}",
                border_style="yellow",
            )
        )

    def show_step(self, session: Session, step_number: int) -> None:
        """Print a single step with full output."""
        step = session.get_step(step_number)
        if step is None:
            self._console.print(f"[red]Step {step_number} not found in session.[/red]")
            return
        self._console.print(render_step(step, show_output=True))


def _compute_delays(steps: list, speed: float) -> list:
    """
    Compute inter-step delays from timestamps.

    Returns a list of floats (seconds to wait BEFORE displaying each step).
    The first step always has delay 0.
    """
    if len(steps) <= 1:
        return [0.0] * len(steps)

    delays = [0.0]
    for i in range(1, len(steps)):
        prev_ts = steps[i - 1].timestamp
        curr_ts = steps[i].timestamp
        raw_delay = (curr_ts - prev_ts).total_seconds()
        # Clamp to sane range (0 to 10 seconds) so we don't wait forever
        clamped = max(0.0, min(raw_delay, 10.0))
        adjusted = clamped / max(speed, 0.01)
        delays.append(adjusted)

    return delays

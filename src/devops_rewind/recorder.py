"""
Session recorder for devops-rewind.

Uses a command-by-command approach: reads commands from the user,
executes each via subprocess.run, and records command + output + metadata.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from typing import Callable, Optional

from rich.console import Console
from rich.panel import Panel

from devops_rewind.session import Session, Step
from devops_rewind.storage import Storage

console = Console()

_ENV_KEYS_TO_SNAPSHOT = ("PATH", "HOME", "PWD", "SHELL", "USER", "LANG")


def _capture_env() -> dict:
    """Capture a safe subset of environment variables."""
    return {k: os.environ.get(k, "") for k in _ENV_KEYS_TO_SNAPSHOT if k in os.environ}


class SessionRecorder:
    """Records terminal commands one-by-one into a Session."""

    def __init__(
        self,
        session: Session,
        storage: Optional[Storage] = None,
        shell: Optional[str] = None,
        on_step: Optional[Callable[[Step], None]] = None,
    ) -> None:
        self.session = session
        self.storage = storage
        self.shell = shell or os.environ.get("SHELL", "/bin/bash")
        self.on_step = on_step
        self._cwd = os.getcwd()

    @property
    def cwd(self) -> str:
        return self._cwd

    def record(self) -> Session:
        """
        Enter the interactive recording loop.

        The user types commands at a custom prompt. Each command is executed
        via the configured shell and its output/exit code are recorded.
        Type 'exit' or press Ctrl-D to end the session.
        """
        console.print(
            Panel(
                f"[bold green]Recording session:[/bold green] [cyan]{self.session.name}[/cyan]\n"
                f"[dim]Shell: {self.shell}[/dim]\n"
                f"[dim]Type commands normally. Type [bold]exit[/bold] or press Ctrl-D to stop.[/dim]",
                title="[bold]devops-rewind[/bold]",
                border_style="green",
            )
        )

        step_number = 0

        while True:
            try:
                prompt = f"[{step_number}] {self._cwd} $ "
                try:
                    command = input(prompt)
                except EOFError:
                    console.print("\n[yellow]EOF received — stopping recording.[/yellow]")
                    break

                command = command.strip()
                if not command:
                    continue

                if command in ("exit", "quit"):
                    console.print("[yellow]Stopping recording.[/yellow]")
                    break

                # Handle 'cd' specially so the working directory updates
                if command.startswith("cd"):
                    step = self._handle_cd(command, step_number)
                else:
                    step = self._run_command(command, step_number)

                self.session.add_step(step)

                if self.on_step:
                    self.on_step(step)

                # Persist after each step so we don't lose data on crash
                if self.storage:
                    self.storage.save_session(self.session)

                step_number += 1

            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted — stopping recording.[/yellow]")
                break

        total = self.session.total_steps
        console.print(
            Panel(
                f"[bold green]Session saved:[/bold green] [cyan]{self.session.id}[/cyan]\n"
                f"[dim]Name: {self.session.name}[/dim]\n"
                f"[dim]Total steps recorded: {total}[/dim]",
                title="[bold]devops-rewind[/bold]",
                border_style="blue",
            )
        )

        if self.storage:
            self.storage.save_session(self.session)

        return self.session

    def record_single(self, command: str) -> Step:
        """
        Record a single command without entering the interactive loop.

        Useful for programmatic usage and testing.
        """
        command = command.strip()
        step_number = self.session.total_steps

        if command.startswith("cd"):
            step = self._handle_cd(command, step_number)
        else:
            step = self._run_command(command, step_number)

        self.session.add_step(step)
        if self.on_step:
            self.on_step(step)
        if self.storage:
            self.storage.save_session(self.session)
        return step

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_command(self, command: str, step_number: int) -> Step:
        """Execute a command and return a Step with its output."""
        timestamp = datetime.now(timezone.utc)
        env_snapshot = _capture_env()
        env_snapshot["PWD"] = self._cwd

        try:
            result = subprocess.run(
                command,
                shell=True,
                executable=self.shell,
                capture_output=True,
                text=True,
                cwd=self._cwd,
                timeout=300,
            )
            combined_output = result.stdout
            if result.stderr:
                combined_output += result.stderr
            exit_code = result.returncode
        except subprocess.TimeoutExpired:
            combined_output = "[devops-rewind: command timed out after 300s]"
            exit_code = 124
        except Exception as exc:
            combined_output = f"[devops-rewind: error running command: {exc}]"
            exit_code = 1

        output = combined_output.rstrip("\n")

        if output:
            if exit_code == 0:
                console.print(output)
            else:
                console.print(f"[red]{output}[/red]")
        if exit_code != 0:
            console.print(f"[red dim]exit code: {exit_code}[/red dim]")

        return Step(
            step_number=step_number,
            command=command,
            output=output,
            exit_code=exit_code,
            timestamp=timestamp,
            cwd=self._cwd,
            env_snapshot=env_snapshot,
        )

    def _handle_cd(self, command: str, step_number: int) -> Step:
        """Handle 'cd' by updating internal cwd."""
        timestamp = datetime.now(timezone.utc)
        env_snapshot = _capture_env()
        env_snapshot["PWD"] = self._cwd

        parts = command.split(maxsplit=1)
        target = parts[1] if len(parts) > 1 else os.path.expanduser("~")
        target = os.path.expanduser(target)

        if not os.path.isabs(target):
            target = os.path.join(self._cwd, target)
        target = os.path.normpath(target)

        if os.path.isdir(target):
            self._cwd = target
            output = ""
            exit_code = 0
        else:
            output = f"cd: no such file or directory: {target}"
            exit_code = 1
            console.print(f"[red]{output}[/red]")

        return Step(
            step_number=step_number,
            command=command,
            output=output,
            exit_code=exit_code,
            timestamp=timestamp,
            cwd=self._cwd,
            env_snapshot=env_snapshot,
        )

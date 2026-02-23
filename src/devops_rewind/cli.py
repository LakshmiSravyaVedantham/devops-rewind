"""
Click CLI entry point for devops-rewind.
"""

from __future__ import annotations

import json
import os
from typing import Optional

import click
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from devops_rewind import __version__
from devops_rewind.branching import branch_session as do_branch
from devops_rewind.breakpoints import BreakpointManager
from devops_rewind.display import (
    render_diff_side_by_side,
    render_sessions_table,
)
from devops_rewind.player import SessionPlayer
from devops_rewind.recorder import SessionRecorder
from devops_rewind.session import Session
from devops_rewind.storage import Storage

console = Console()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_storage() -> Storage:
    return Storage()


def _resolve_session(storage: Storage, session_id: str) -> Session:
    """Load a session by ID (or by name as fallback). Exit on failure."""
    session = storage.load_session(session_id)
    if session is None:
        session = storage.find_session_by_name(session_id)
    if session is None:
        console.print(f"[red]Session not found: {session_id!r}[/red]")
        raise SystemExit(1)
    return session


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------


@click.group()
@click.version_option(__version__, prog_name="devops-rewind")
def main() -> None:
    """devops-rewind — Terminal session debugger with rewind and breakpoints.

    Record terminal sessions, set breakpoints, and replay or rewind to any step.
    When a deploy script fails at step 47, rewind to step 45 and try a different path.
    """


# ---------------------------------------------------------------------------
# record
# ---------------------------------------------------------------------------


@main.command("record")
@click.argument("name", default="")
@click.option("--shell", default="", help="Shell to use (default: $SHELL or /bin/bash)")
def cmd_record(name: str, shell: str) -> None:
    """Start recording a new terminal session.

    NAME is an optional label for the session. If omitted, a timestamp-based
    name is generated automatically.

    Type commands at the prompt. Type 'exit' or press Ctrl-D to finish.
    """
    from datetime import datetime, timezone

    if not name:
        name = f"session-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    shell_bin = shell or os.environ.get("SHELL", "/bin/bash")
    storage = _get_storage()
    session = Session.new(name)
    recorder = SessionRecorder(session=session, storage=storage, shell=shell_bin)
    recorder.record()


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@main.command("list")
@click.option("--limit", default=20, show_default=True, help="Number of sessions to show.")
@click.option(
    "--format",
    "fmt",
    default="table",
    type=click.Choice(["table", "json"]),
    show_default=True,
    help="Output format.",
)
def cmd_list(limit: int, fmt: str) -> None:
    """List all recorded sessions."""
    storage = _get_storage()
    sessions = storage.list_sessions(limit=limit)

    if not sessions:
        console.print("[yellow]No sessions recorded yet. Run 'devops-rewind record' to start.[/yellow]")
        return

    if fmt == "json":
        data = [
            {
                "id": s.id,
                "name": s.name,
                "created_at": s.created_at.isoformat(),
                "total_steps": s.total_steps,
                "is_branch": s.is_branch,
            }
            for s in sessions
        ]
        click.echo(json.dumps(data, indent=2))
    else:
        console.print(render_sessions_table(sessions))


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------


@main.command("replay")
@click.argument("session_id")
@click.option("--speed", default=1.0, show_default=True, help="Playback speed multiplier.")
@click.option("--step", "step_mode", is_flag=True, help="Step-by-step mode (press Enter to advance).")
@click.option("--from", "from_step", default=0, show_default=True, help="Start from step number.")
@click.option("--to", "to_step", default=None, type=int, help="Stop at step number.")
def cmd_replay(session_id: str, speed: float, step_mode: bool, from_step: int, to_step: Optional[int]) -> None:
    """Replay a recorded session.

    SESSION_ID can be a full UUID or a session name.
    """
    storage = _get_storage()
    session = _resolve_session(storage, session_id)
    player = SessionPlayer()
    player.replay(session, speed=speed, step_mode=step_mode, from_step=from_step, to_step=to_step)


# ---------------------------------------------------------------------------
# rewind
# ---------------------------------------------------------------------------


@main.command("rewind")
@click.argument("session_id")
@click.argument("step", type=int)
@click.option(
    "--exec",
    "re_exec",
    is_flag=True,
    help="Re-execute the session from this step in a new recording branch.",
)
def cmd_rewind(session_id: str, step: int, re_exec: bool) -> None:
    """Jump to a specific step in a session and show the state at that point.

    SESSION_ID can be a full UUID or a session name.
    STEP is the step number to rewind to.
    """
    storage = _get_storage()
    session = _resolve_session(storage, session_id)
    player = SessionPlayer()
    player.rewind(session, step)

    if re_exec:
        console.print(
            Panel(
                f"[bold yellow]Branching from step {step} into a new recording session…[/bold yellow]\n"
                "[dim]A new session will be created with the history up to this step.[/dim]",
                border_style="yellow",
            )
        )
        new_session = do_branch(session, from_step=step, storage=storage)
        recorder = SessionRecorder(session=new_session, storage=storage)
        # Pre-populate cwd from the step's working directory
        target_step = session.get_step(step)
        if target_step:
            recorder._cwd = target_step.cwd
        recorder.record()


# ---------------------------------------------------------------------------
# breakpoint (group)
# ---------------------------------------------------------------------------


@main.group("breakpoint")
def bp_group() -> None:
    """Manage breakpoints for a session."""


@bp_group.command("add")
@click.argument("session_id")
@click.argument("step", type=int, default=-1)
@click.option("--pattern", default=None, help="Regex pattern to match against commands.")
@click.option("--on-error", is_flag=True, help="Break on any non-zero exit code.")
def cmd_bp_add(session_id: str, step: int, pattern: Optional[str], on_error: bool) -> None:
    """Add a breakpoint to a session.

    SESSION_ID can be a full UUID or a session name.
    STEP is the step number (use -1 to omit a step-based trigger).
    """
    storage = _get_storage()
    session = _resolve_session(storage, session_id)
    mgr = BreakpointManager(session_id=session.id, storage=storage)

    step_arg = step if step >= 0 else None
    if step_arg is None and pattern is None and not on_error:
        console.print("[red]Specify at least one of: STEP >= 0, --pattern, or --on-error.[/red]")
        raise SystemExit(1)

    try:
        bp = mgr.add(step_number=step_arg, pattern=pattern, on_error=on_error)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1)

    console.print(f"[green]Breakpoint added:[/green] {bp.describe()}")


@bp_group.command("list")
@click.argument("session_id")
def cmd_bp_list(session_id: str) -> None:
    """List all breakpoints for a session."""
    storage = _get_storage()
    session = _resolve_session(storage, session_id)
    mgr = BreakpointManager(session_id=session.id, storage=storage)
    bps = mgr.list()

    if not bps:
        console.print("[yellow]No breakpoints set for this session.[/yellow]")
        return

    table = Table(title="Breakpoints", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Step", justify="right")
    table.add_column("Pattern")
    table.add_column("On Error", justify="center")

    for bp in bps:
        table.add_row(
            str(bp.id),
            str(bp.step_number) if bp.step_number is not None else "—",
            bp.pattern or "—",
            "[red]yes[/red]" if bp.on_error else "no",
        )
    console.print(table)


@bp_group.command("remove")
@click.argument("session_id")
@click.argument("bp_id", type=int)
def cmd_bp_remove(session_id: str, bp_id: int) -> None:
    """Remove a breakpoint by its ID."""
    storage = _get_storage()
    session = _resolve_session(storage, session_id)
    mgr = BreakpointManager(session_id=session.id, storage=storage)
    removed = mgr.remove(bp_id)
    if removed:
        console.print(f"[green]Breakpoint {bp_id} removed.[/green]")
    else:
        console.print(f"[red]Breakpoint {bp_id} not found.[/red]")


# ---------------------------------------------------------------------------
# branch
# ---------------------------------------------------------------------------


@main.command("branch")
@click.argument("session_id")
@click.argument("step", type=int)
@click.option("--name", default=None, help="Name for the new branch session.")
@click.option(
    "--exec",
    "re_exec",
    is_flag=True,
    help="Open a recording shell in the new branch after creating it.",
)
def cmd_branch(session_id: str, step: int, name: Optional[str], re_exec: bool) -> None:
    """Fork a session from a given step, creating a new branch session.

    SESSION_ID can be a full UUID or a session name.
    STEP is the step number to fork from.
    """
    storage = _get_storage()
    session = _resolve_session(storage, session_id)

    try:
        new_session = do_branch(session, from_step=step, new_name=name, storage=storage)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1)

    console.print(
        Panel(
            f"[green]Branch created:[/green] [cyan]{new_session.id}[/cyan]\n"
            f"Name: [bold]{new_session.name}[/bold]\n"
            f"Forked from: [dim]{session.name}[/dim] at step {step}\n"
            f"History steps copied: {new_session.total_steps}",
            title="[bold]Branch Created[/bold]",
            border_style="green",
        )
    )

    if re_exec:
        console.print("[yellow]Starting recording in the new branch…[/yellow]")
        recorder = SessionRecorder(session=new_session, storage=storage)
        target_step = session.get_step(step)
        if target_step:
            recorder._cwd = target_step.cwd
        recorder.record()


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------


@main.command("diff")
@click.argument("session_a")
@click.argument("session_b")
@click.option("--from", "from_step", default=0, show_default=True, help="Compare from this step.")
def cmd_diff(session_a: str, session_b: str, from_step: int) -> None:
    """Compare two sessions side by side.

    SESSION_A and SESSION_B can be full UUIDs or session names.
    """
    storage = _get_storage()
    sess_a = _resolve_session(storage, session_a)
    sess_b = _resolve_session(storage, session_b)
    render_diff_side_by_side(sess_a, sess_b, from_step=from_step)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@main.command("delete")
@click.argument("session_id")
@click.confirmation_option(prompt="Are you sure you want to delete this session?")
def cmd_delete(session_id: str) -> None:
    """Delete a recorded session and all its steps.

    SESSION_ID can be a full UUID or a session name.
    """
    storage = _get_storage()
    session = _resolve_session(storage, session_id)
    deleted = storage.delete_session(session.id)
    if deleted:
        console.print(f"[green]Session '{session.name}' ({session.id[:8]}…) deleted.[/green]")
    else:
        console.print("[red]Failed to delete session.[/red]")


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


@main.command("export")
@click.argument("session_id")
@click.option(
    "--format",
    "fmt",
    default="sh",
    type=click.Choice(["sh", "markdown", "json"]),
    show_default=True,
    help="Export format.",
)
def cmd_export(session_id: str, fmt: str) -> None:
    """Export a session as a shell script, Markdown, or JSON.

    SESSION_ID can be a full UUID or a session name.

    Output is printed to stdout so you can redirect it to a file:

        devops-rewind export my-session --format sh > deploy.sh
    """
    storage = _get_storage()
    session = _resolve_session(storage, session_id)

    if fmt == "json":
        click.echo(json.dumps(session.to_dict(), indent=2))

    elif fmt == "sh":
        lines = [
            "#!/usr/bin/env bash",
            f"# Session: {session.name}",
            f"# Recorded: {session.created_at.isoformat()}",
            f"# Steps: {session.total_steps}",
            "set -e",
            "",
        ]
        for step in session.steps:
            lines.append(f"# Step {step.step_number} — exit {step.exit_code}")
            lines.append(f"cd {step.cwd}")
            lines.append(step.command)
            lines.append("")
        click.echo("\n".join(lines))

    elif fmt == "markdown":
        lines = [
            f"# Session: {session.name}",
            "",
            f"- **ID**: `{session.id}`",
            f"- **Recorded**: {session.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"- **Steps**: {session.total_steps}",
            "",
            "## Steps",
            "",
        ]
        for step in session.steps:
            status = "OK" if step.succeeded else f"FAILED (exit {step.exit_code})"
            lines.append(f"### Step {step.step_number} — {status}")
            lines.append(f"**Directory**: `{step.cwd}`")
            lines.append("")
            lines.append("```bash")
            lines.append(f"$ {step.command}")
            if step.output:
                lines.append(step.output)
            lines.append("```")
            lines.append("")
        click.echo("\n".join(lines))


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


@main.command("version")
def cmd_version() -> None:
    """Show the devops-rewind version."""
    console.print(
        Panel(
            f"[bold cyan]devops-rewind[/bold cyan] v[bold]{__version__}[/bold]",
            border_style="blue",
        )
    )

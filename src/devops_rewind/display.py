"""
Rich terminal display utilities for devops-rewind.
"""

from __future__ import annotations

from typing import List

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

from devops_rewind.session import Session, Step

console = Console()


def _exit_style(exit_code: int) -> str:
    if exit_code == 0:
        return "green"
    return "red"


def _exit_label(exit_code: int) -> str:
    if exit_code == 0:
        return "[green]OK[/green]"
    return f"[red]ERR {exit_code}[/red]"


def render_step(step: Step, show_output: bool = True) -> Panel:
    """Render a single step as a Rich Panel."""
    style = _exit_style(step.exit_code)
    header = Text()
    header.append(f"Step {step.step_number}", style="bold cyan")
    header.append("  ")
    header.append(step.command, style="bold white")
    header.append("  ")
    header.append(_exit_label(step.exit_code))
    header.append(f"  [dim]{step.cwd}[/dim]")

    body_lines = []
    if show_output and step.output:
        if step.exit_code == 0:
            body_lines.append(Text(step.output, style="white"))
        else:
            body_lines.append(Text(step.output, style="red"))
    else:
        body_lines.append(Text("[dim](no output)[/dim]"))

    ts = step.timestamp.strftime("%H:%M:%S") if step.timestamp else ""
    body_lines.append(Text(f"\n[dim]@ {ts}  cwd: {step.cwd}[/dim]"))

    from rich.console import Group

    content = Group(*body_lines)
    return Panel(content, title=header, border_style=style, expand=True)


def render_session_info(session: Session) -> Panel:
    """Render a summary panel for a session."""
    lines = [
        f"[bold cyan]ID:[/bold cyan]      {session.id}",
        f"[bold cyan]Name:[/bold cyan]    {session.name}",
        f"[bold cyan]Created:[/bold cyan] {session.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"[bold cyan]Steps:[/bold cyan]   {session.total_steps}",
    ]
    if session.duration is not None:
        lines.append(f"[bold cyan]Duration:[/bold cyan] {session.duration:.1f}s")
    if session.is_branch:
        lines.append(f"[bold yellow]Branch of:[/bold yellow] {session.parent_id} (from step {session.fork_step})")

    failed = sum(1 for s in session.steps if s.failed)
    if failed:
        lines.append(f"[bold red]Failures:[/bold red] {failed} step(s)")
    else:
        lines.append("[bold green]All steps succeeded[/bold green]")

    return Panel("\n".join(lines), title="[bold]Session Info[/bold]", border_style="blue")


def render_sessions_table(sessions: List[Session]) -> Table:
    """Render a list of sessions as a Rich Table."""
    table = Table(
        title="[bold]Recorded Sessions[/bold]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("ID (short)", style="cyan", no_wrap=True, width=10)
    table.add_column("Name", style="white")
    table.add_column("Created", style="dim", no_wrap=True)
    table.add_column("Steps", justify="right", style="magenta")
    table.add_column("Duration", justify="right", style="dim")
    table.add_column("Failures", justify="right")
    table.add_column("Branch?", justify="center")

    for s in sessions:
        duration_str = f"{s.duration:.1f}s" if s.duration is not None else "—"
        failed = sum(1 for step in s.steps if step.failed)
        failure_str = f"[red]{failed}[/red]" if failed else "[green]0[/green]"
        branch_str = "[yellow]yes[/yellow]" if s.is_branch else "no"
        table.add_row(
            s.id[:8],
            s.name,
            s.created_at.strftime("%Y-%m-%d %H:%M"),
            str(s.total_steps),
            duration_str,
            failure_str,
            branch_str,
        )

    return table


def render_diff_side_by_side(
    session_a: Session,
    session_b: Session,
    from_step: int = 0,
) -> None:
    """Print a side-by-side diff of two sessions using Rich Columns."""
    max_steps = max(session_a.total_steps, session_b.total_steps)

    console.print(
        Panel(
            f"[bold cyan]{session_a.name}[/bold cyan] ({session_a.id[:8]})  vs  "
            f"[bold magenta]{session_b.name}[/bold magenta] ({session_b.id[:8]})",
            title="[bold]Session Diff[/bold]",
            border_style="blue",
        )
    )

    diverged = False
    for i in range(from_step, max_steps):
        step_a = session_a.get_step(i)
        step_b = session_b.get_step(i)

        cmd_a = step_a.command if step_a else "[dim](no step)[/dim]"
        cmd_b = step_b.command if step_b else "[dim](no step)[/dim]"

        same_cmd = step_a is not None and step_b is not None and step_a.command == step_b.command

        if not same_cmd and not diverged:
            console.print(f"\n[bold yellow]--- Sessions diverge at step {i} ---[/bold yellow]\n")
            diverged = True

        style_a = "green" if (step_a and step_a.succeeded) else "red"
        style_b = "green" if (step_b and step_b.succeeded) else "red"

        left = Panel(
            Text.assemble(
                (f"$ {cmd_a}\n", f"bold {style_a}"),
                (step_a.output[:200] if step_a and step_a.output else "", "dim"),
            ),
            title=f"[cyan]A: Step {i}[/cyan]",
            border_style=style_a,
        )
        right = Panel(
            Text.assemble(
                (f"$ {cmd_b}\n", f"bold {style_b}"),
                (step_b.output[:200] if step_b and step_b.output else "", "dim"),
            ),
            title=f"[magenta]B: Step {i}[/magenta]",
            border_style=style_b,
        )

        console.print(Columns([left, right], equal=True, expand=True))

    if not diverged:
        console.print("[green]Sessions are identical in the compared range.[/green]")


def make_replay_progress() -> Progress:
    """Return a Rich Progress bar configured for replay."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    )

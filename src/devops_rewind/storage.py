"""
SQLite-backed persistent storage for devops-rewind sessions, steps, and breakpoints.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import List, Optional

from dateutil.parser import parse as parse_dt

from devops_rewind.session import Session, Step

DEFAULT_DB_DIR = Path.home() / ".devops-rewind"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "sessions.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    parent_id   TEXT,
    fork_step   INTEGER
);

CREATE TABLE IF NOT EXISTS steps (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    step_number  INTEGER NOT NULL,
    command      TEXT NOT NULL,
    output       TEXT NOT NULL,
    exit_code    INTEGER NOT NULL,
    timestamp    TEXT NOT NULL,
    cwd          TEXT NOT NULL,
    env_snapshot TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS breakpoints (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    step_number  INTEGER,
    pattern      TEXT,
    on_error     INTEGER NOT NULL DEFAULT 0
);
"""


class Storage:
    """Manages SQLite persistence for sessions, steps, and breakpoints."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def save_session(self, session: Session) -> None:
        """Insert or replace a session and all its steps."""
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO sessions (id, name, created_at, parent_id, fork_step)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session.id,
                    session.name,
                    session.created_at.isoformat(),
                    session.parent_id,
                    session.fork_step,
                ),
            )
            # Remove old steps and reinsert (simplest upsert strategy)
            self._conn.execute("DELETE FROM steps WHERE session_id = ?", (session.id,))
            for step in session.steps:
                self._conn.execute(
                    """
                    INSERT INTO steps
                        (session_id, step_number, command, output, exit_code, timestamp, cwd, env_snapshot)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session.id,
                        step.step_number,
                        step.command,
                        step.output,
                        step.exit_code,
                        step.timestamp.isoformat(),
                        step.cwd,
                        json.dumps(step.env_snapshot),
                    ),
                )

    def load_session(self, session_id: str) -> Optional[Session]:
        """Load a session (with steps) by ID."""
        row = self._conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_session(row)

    def list_sessions(self, limit: Optional[int] = None) -> List[Session]:
        """Return all sessions ordered by creation date descending."""
        query = "SELECT * FROM sessions ORDER BY created_at DESC"
        if limit is not None:
            query += f" LIMIT {int(limit)}"
        rows = self._conn.execute(query).fetchall()
        return [self._row_to_session(r) for r in rows]

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and cascade-delete its steps and breakpoints."""
        with self._conn:
            cursor = self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        return cursor.rowcount > 0

    def session_exists(self, session_id: str) -> bool:
        """Return True if a session with the given ID exists."""
        row = self._conn.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return row is not None

    def find_session_by_name(self, name: str) -> Optional[Session]:
        """Return the most recent session with the given name, or None."""
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE name = ? ORDER BY created_at DESC LIMIT 1",
            (name,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_session(row)

    # ------------------------------------------------------------------
    # Breakpoints
    # ------------------------------------------------------------------

    def add_breakpoint(
        self, session_id: str, step_number: Optional[int], pattern: Optional[str], on_error: bool
    ) -> int:
        """Insert a breakpoint and return its ID."""
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO breakpoints (session_id, step_number, pattern, on_error)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, step_number, pattern, int(on_error)),
            )
        return cursor.lastrowid  # type: ignore[return-value]

    def list_breakpoints(self, session_id: str) -> List[dict]:
        """Return all breakpoints for a session."""
        rows = self._conn.execute(
            "SELECT * FROM breakpoints WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def remove_breakpoint(self, bp_id: int) -> bool:
        """Remove a breakpoint by ID."""
        with self._conn:
            cursor = self._conn.execute("DELETE FROM breakpoints WHERE id = ?", (bp_id,))
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _row_to_session(self, row: sqlite3.Row) -> Session:
        steps_rows = self._conn.execute(
            "SELECT * FROM steps WHERE session_id = ? ORDER BY step_number",
            (row["id"],),
        ).fetchall()
        steps = [
            Step(
                step_number=r["step_number"],
                command=r["command"],
                output=r["output"],
                exit_code=r["exit_code"],
                timestamp=parse_dt(r["timestamp"]),
                cwd=r["cwd"],
                env_snapshot=json.loads(r["env_snapshot"]),
            )
            for r in steps_rows
        ]
        return Session(
            id=row["id"],
            name=row["name"],
            created_at=parse_dt(row["created_at"]),
            steps=steps,
            parent_id=row["parent_id"],
            fork_step=row["fork_step"],
        )

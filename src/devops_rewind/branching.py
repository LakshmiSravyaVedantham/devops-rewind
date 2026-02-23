"""
Session branching (forking) for devops-rewind.

Allows forking a session from any step, creating a new session that
starts with the history up to that point, ready for divergent replay.
"""

from __future__ import annotations

import copy
from typing import Optional

from devops_rewind.session import Session
from devops_rewind.storage import Storage


def branch_session(
    original_session: Session,
    from_step: int,
    new_name: Optional[str] = None,
    storage: Optional[Storage] = None,
) -> Session:
    """
    Fork a session from a given step, creating a new session.

    The new session contains all steps from 0 up to (and including) from_step,
    preserving the original history. The parent_id and fork_step are set so
    the lineage can be tracked and diff'd later.

    Args:
        original_session:  The session to fork.
        from_step:         The step number to fork from (inclusive).
        new_name:          Name for the new branch. Defaults to
                           "<original_name>-branch-<from_step>".
        storage:           If provided, the new session is persisted immediately.

    Returns:
        A new Session with steps 0..from_step copied from the original.

    Raises:
        ValueError: If from_step is out of range for the original session.
    """
    if original_session.total_steps == 0:
        raise ValueError("Cannot branch from an empty session.")

    max_step = original_session.total_steps - 1
    if from_step < 0 or from_step > max_step:
        raise ValueError(
            f"from_step={from_step} is out of range for session " f"'{original_session.name}' (valid: 0–{max_step})."
        )

    branch_name = new_name or f"{original_session.name}-branch-{from_step}"

    new_session = Session.new(
        name=branch_name,
        parent_id=original_session.id,
        fork_step=from_step,
    )

    # Deep-copy the steps so mutations in the branch don't affect the original
    for step in original_session.steps:
        if step.step_number <= from_step:
            copied = copy.deepcopy(step)
            new_session.add_step(copied)

    if storage is not None:
        storage.save_session(new_session)

    return new_session


def get_branch_lineage(session: Session, storage: Storage) -> list:
    """
    Return the chain of sessions from the root to the given session.

    Walks the parent_id links back to the original session.

    Returns:
        List of Session objects from oldest ancestor to current session.
    """
    chain = [session]
    current = session
    seen_ids = {session.id}

    while current.parent_id is not None:
        if current.parent_id in seen_ids:
            # Cycle guard
            break
        parent = storage.load_session(current.parent_id)
        if parent is None:
            break
        chain.insert(0, parent)
        seen_ids.add(parent.id)
        current = parent

    return chain

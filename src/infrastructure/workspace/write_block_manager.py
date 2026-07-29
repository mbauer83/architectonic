"""Compat shim — per-repo write block backed by WorkspaceMutationGate.

New code should use ``mutation_gate.get_workspace_gate()`` directly.  This
module preserves the ``block_repo`` / ``unblock_repo`` / ``is_blocked`` API
consumed by git_sync.py until WS8 migrates those callers to the gate's
``blocking_writes()`` context manager.

One process serves one workspace, so all roots share a single gate.  The
``repo_root`` parameter is accepted for API compatibility but is not used for
gate selection.
"""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.workspace.mutation_gate import BlockReason, get_workspace_gate


def block_repo(repo_root: Path, *, reason: BlockReason = "sync_in_progress") -> None:  # noqa: ARG001
    """Signal that writes are blocked for this workspace.

    Never downgrades ``read_only`` to ``sync_in_progress`` — a permanent
    read-only gate must not be temporarily overridden by a transient sync.
    """
    gate = get_workspace_gate()
    if gate.block_reason == "read_only" and reason != "read_only":
        return
    gate.set_block(reason)


def unblock_repo(repo_root: Path) -> None:  # noqa: ARG001
    """Clear the write block for this workspace.

    Never clears a ``read_only`` block — that mode is permanent for the
    process lifetime and must not be undone by a sync completing.
    """
    gate = get_workspace_gate()
    if gate.block_reason == "read_only":
        return
    gate.clear_block()


def is_blocked(repo_root: Path) -> bool:  # noqa: ARG001
    """Return True if any write block is currently active."""
    return get_workspace_gate().block_reason is not None

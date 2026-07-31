"""Nodes that predate mandatory provenance, and the one thing that may be done to them.

A node with no provenance records nothing about which analysis produced it. There were 26 such
nodes in the live store when the invariant was introduced, and they are kept — deleting evidence
of past work to satisfy a new rule would be worse than the gap. They are *readable*, and they are
visible in the repair surface with every relation intact.

But they are **repair-only**. Assigning provenance is the sole mutation permitted: no ordinary
edit, no new participation, no new edge, no factor assessment. Without that, an unattributed node
stays fully active while the invariant is nominally being restored — new work accumulates against
a record that cannot say who produced it, and the backlog stops shrinking because nothing stops it
growing.

The check lives here rather than in each use case so the rule has one statement. Each write path
calls it before doing anything, and the refusal names the node and the one operation that is
allowed, so a caller is told what to do rather than only what failed.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.assurance_ports import ConfidentialAssuranceStore

#: The only operation permitted against a legacy-invalid node.
PERMITTED_OPERATION = "assign_provenance"


@dataclass(frozen=True)
class LegacyInvalidNode:
    """The node predates mandatory provenance, so only provenance assignment may touch it."""

    node_id: str
    permitted_operation: str = PERMITTED_OPERATION

    @property
    def message(self) -> str:
        return (
            f"Node {self.node_id!r} records no analysis that produced it. Assign its provenance "
            f"first — until then {PERMITTED_OPERATION} is the only operation permitted on it."
        )


def is_legacy_invalid(node: dict[str, object] | None) -> bool:
    """Whether a node row predates mandatory provenance. A missing node is not this problem."""
    return node is not None and not str(node.get("analysis_id") or "")


def refuse_if_legacy_invalid(
    store: ConfidentialAssuranceStore, node_id: str
) -> LegacyInvalidNode | None:
    """The refusal for a node awaiting provenance repair, or None when the node may be mutated.

    Returns None for a node that does not exist: absence is a different answer with a different
    remedy, and the caller's own not-found handling is the one that should report it.
    """
    node = store.get_node(node_id)
    if is_legacy_invalid(node):
        return LegacyInvalidNode(node_id=node_id)
    return None

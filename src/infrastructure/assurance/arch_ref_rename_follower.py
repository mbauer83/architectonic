"""Keeping assurance references spelled the way architecture spells them.

An assurance node's reference to an architecture artifact stays *resolvable* across a rename —
identity is the id's stem — but it is read by someone reviewing a safety argument, where the name is
all they see, so a reference naming a title the artifact no longer has is actively misleading.

The store follows only when it is **unlocked**. A locked or absent store is the ordinary case for a
session that never opened the confidential tier, and it is not a reason to refuse or delay an
architecture write: the references still resolve, and the next rename heals them, because matching is
on the stem rather than on the slug this rename started from.
"""

from __future__ import annotations

from src.application.rename_followers import ArtifactRenamed, register_rename_follower


def follow_rename_into_assurance(rename: ArtifactRenamed) -> tuple[str, ...]:
    """Retarget assurance references to the renamed artifact, when the store is open to us.

    The store is reached exactly as every other confidential-tier caller reaches it — through the
    workspace-keyed bundle — so there is no second way to open it, and no way for this path to open
    one that is closed.
    """
    from src.infrastructure.mcp.assurance_mcp.context import AssuranceContext  # noqa: PLC0415

    try:
        store = AssuranceContext().store
    except Exception:  # noqa: BLE001 - no confidential tier configured for this workspace
        return ()
    if not store.is_unlocked():
        return ()
    moved = store.retarget_arch_refs(new_arch_artifact_id=rename.new_artifact_id)
    if not moved:
        return ()
    plural = "reference" if moved == 1 else "references"
    return (f"Retargeted {moved} assurance {plural} to {rename.new_artifact_id}.",)


register_rename_follower(follow_rename_into_assurance)

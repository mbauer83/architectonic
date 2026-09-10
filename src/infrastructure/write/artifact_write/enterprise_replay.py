"""Re-applying a recorded edit to the enterprise repository, through its sanctioned writers.

`admin_ops` is the only authorised way into that repository, and this dispatches a recorded edit
across it by the kind the edit declares. Not by reaching for `edit_entity` and friends with an
enterprise root: those refuse one unconditionally, and routing around that refusal is the workaround
this project forbids by name.

**Which authority may call this is not decided here.** Admin authoring and change submission are two
authorities over the same repository, and the intent a call site passes to `authorized_write` is what
separates them. This is the writer they share.

The dispatch is spelled out per kind rather than driven from a mapping of arguments: the three
functions do not take the same ones — the entity edit alone needs a registry, and its absent-field
sentinel is not `None` — and a mapping splatted into all three is a claim the type checker cannot
check and the reader cannot follow. Its sibling in `rebase_replay` says the same about the engagement
writers, and the two stay apart because the signatures genuinely differ; what they must agree on is
the *field vocabulary*, which `test_both_authorities_edit_over_one_field_vocabulary` asserts.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from src.application.modeling.proposal_edit import ProposalEdit
from src.infrastructure.write.artifact_write.types import WriteResult

if TYPE_CHECKING:
    from src.application.verification.artifact_verifier import ArtifactVerifier
    from src.application.verification.artifact_verifier_registry import ArtifactRegistry


def apply_to_enterprise(
    edit: ProposalEdit,
    *,
    enterprise_root: Path,
    registry: "ArtifactRegistry",
    verifier: "ArtifactVerifier",
    clear_repo_caches: Callable[[Path], None],
) -> WriteResult:
    """Make `edit` in the enterprise repository, returning what the write path answered."""
    from src.infrastructure.write.artifact_write.admin_ops import (  # noqa: PLC0415
        admin_edit_diagram,
        admin_edit_document,
        admin_edit_entity,
    )

    match edit.kind:
        case "document":
            return admin_edit_document(
                repo_root=enterprise_root, verifier=verifier,
                clear_repo_caches=clear_repo_caches, artifact_id=edit.artifact_id,
                dry_run=False, **edit.fields,
            )
        case "diagram":
            return admin_edit_diagram(
                repo_root=enterprise_root, verifier=verifier,
                clear_repo_caches=clear_repo_caches, artifact_id=edit.artifact_id,
                dry_run=False, **edit.fields,
            )
        case _:
            return admin_edit_entity(
                repo_root=enterprise_root, registry=registry, verifier=verifier,
                clear_repo_caches=clear_repo_caches, artifact_id=edit.artifact_id,
                dry_run=False, **edit.fields,
            )

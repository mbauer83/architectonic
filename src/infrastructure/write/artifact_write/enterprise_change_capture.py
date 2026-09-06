"""Turning an edit of enterprise-owned content into a recorded change instead of a refusal.

An engagement repository holds a *reference* to a promoted artifact, not the artifact. Editing one
therefore has nowhere to write, and until now the write path discovered that the hard way: it edited
the reference, dropped the field naming what it stands for, and failed verification with `E140` —
a message about a symptom of its own write rather than about what the author did. The GUI was quieter
and no better, hiding the edit affordance with no explanation and no path forward.

So the edit is recorded. The author changed the artifact they were shown, and what they were shown
already carried their earlier change; the recorded change is that intent, replayed later against
whatever the enterprise artifact has become.

**The sentinel is the vocabulary.** `edit_entity` distinguishes "not given" from "given as empty" with
`_UNSET`, because clearing a summary and leaving it alone are different edits. A change records only
what was *given*, so that distinction is the one thing this must not lose — collapsing it would make
every recorded change claim to blank every field the author did not mention.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.application.derivation.refresh import compute_revision
from src.application.modeling.change_recording import UnrecordableChange, decide
from src.application.modeling.proposal_standing import pending_proposals
from src.application.modeling.proposed_change import PROPOSED_CHANGE_TYPE
from src.infrastructure.write.artifact_write.change_materialization import materialize
from src.infrastructure.write.artifact_write.types import WriteResult

if TYPE_CHECKING:
    from src.application.artifacts.query import ArtifactRepository
    from src.application.verification.artifact_verifier import ArtifactVerifier
    from src.application.verification.artifact_verifier_registry import ArtifactRegistry

#: What `edit_entity` passes for a field the caller did not mention. Imported rather than respelled:
#: a second sentinel that merely compares equal would make "not given" and "given" indistinguishable
#: for exactly the fields whose default is falsy.
from src.infrastructure.write.artifact_write.entity_edit import _UNSET  # noqa: E402


def provided_content_fields(**candidates: Any) -> dict[str, Any]:
    """The fields the caller actually gave, in the write call's own vocabulary.

    `None` counts as not given for the plain-string parameters, which is how `edit_entity` reads them
    — they have no sentinel because there is no way to set them to nothing.
    """
    return {
        name: value
        for name, value in candidates.items()
        if value is not _UNSET and value is not None
    }


def record_enterprise_change(
    *,
    repo: "ArtifactRepository | None",
    registry: "ArtifactRegistry",
    verifier: "ArtifactVerifier",
    clear_repo_caches: Callable[[Path], None],
    repo_root: Path,
    reference_id: str,
    target_id: str,
    reference: Any,
    fields: Mapping[str, Any],
    dry_run: bool,
) -> WriteResult:
    """Record `fields` as a change against `target_id`, or say why it cannot be."""
    reference_path = registry.find_file_by_id(reference_id)
    if not fields:
        return _refusal(
            reference_path,
            reference_id,
            "an edit that changes nothing is not a change",
        )
    if repo is None:
        return _refusal(
            reference_path,
            reference_id,
            f"'{reference_id}' stands for the enterprise artifact '{target_id}', which this "
            "repository does not own. The edit would be recorded as a change awaiting review, and "
            "this caller supplied no repository to record it in.",
        )

    pending = pending_proposals(repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE)).get(target_id, ())
    try:
        outcome = decide(kind="entity", target_id=target_id, fields=fields, pending=pending)
    except UnrecordableChange as refused:
        return _refusal(reference_path, reference_id, str(refused))

    return materialize(
        outcome,
        repo=repo,
        engagement_root=repo_root,
        verifier=verifier,
        clear_repo_caches=clear_repo_caches,
        target_name=_display_name(reference, reference_id),
        # What the reference is *now*. Only a first recording uses it; superseding carries the
        # revision its predecessor was written against, which the outcome already holds.
        base_revision=compute_revision(reference_path) if reference_path is not None else "",
        dry_run=dry_run,
    )


def _display_name(reference: Any, reference_id: str) -> str:
    name = getattr(getattr(reference, "frontmatter", None), "get", lambda _k: None)("name")
    return str(name) if isinstance(name, str) and name.strip() else reference_id


def _refusal(path: Path | None, artifact_id: str, message: str) -> WriteResult:
    return WriteResult(
        wrote=False,
        path=path if path is not None else Path(artifact_id),
        artifact_id=artifact_id,
        content=None,
        warnings=[message],
        verification=None,
    )

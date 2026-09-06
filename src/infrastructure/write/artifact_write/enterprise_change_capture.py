"""Turning an edit of enterprise-owned content into a recorded change instead of a refusal.

An engagement repository holds a *reference* to a promoted artifact, not the artifact. Editing one
therefore has nowhere to write, and until now the write path discovered that the hard way: it edited
the reference, dropped the field naming what it stands for, and failed verification with `E140` —
a message about a symptom of its own write rather than about what the author did. The GUI was quieter
and no better, hiding the edit affordance with no explanation and no path forward.

So the edit is recorded. The author changed the artifact they were shown, and what they were shown
already carried their earlier change; the recorded change is that intent, replayed later against
whatever the enterprise artifact has become.

**The kind comes from the reference, never from the caller's assumption.** A reference stands for an
entity, a document or a diagram, and which one decides the vocabulary the recorded change may use.
This module hardcoded `entity`, which was wrong for the promoted document this repository already
holds a reference to: its change would have been recorded under the entity catalogue, and refused
only at replay, in front of whoever was reviewing it.

**The sentinel is the vocabulary, and it is not this module's.** `edit_entity` distinguishes "not
given" from "given as empty"; a diagram edit's `None` already means *clear it*. A change records only
what was *given*, so that distinction is the one thing this must not lose — and a single filter here
would have to know all three vocabularies to be right about any of them.
`enterprise_edit_arguments` holds the three readings; this module is handed the result.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.application.modeling.change_recording import UnrecordableChange, decide
from src.application.modeling.edit_field_catalogue import ArtifactKind
from src.application.modeling.enterprise_reference import enterprise_target, proxied_kind
from src.application.modeling.integration_detection import current_values_of
from src.application.modeling.proposal_standing import enterprise_revision, pending_proposals
from src.application.modeling.proposed_change import PROPOSED_CHANGE_TYPE, UNKNOWN_BASE
from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.write.artifact_write.change_materialization import materialize
from src.infrastructure.write.artifact_write.types import WriteResult

if TYPE_CHECKING:
    from src.application.artifacts.query import ArtifactRepository
    from src.application.verification.artifact_verifier import ArtifactVerifier
    from src.application.verification.artifact_verifier_registry import ArtifactRegistry

def recorded_instead_of_written(
    *,
    kind: ArtifactKind,
    registry: "ArtifactRegistry | None",
    verifier: "ArtifactVerifier",
    clear_repo_caches: Callable[[Path], None],
    repo: "ArtifactRepository | None",
    repo_root: Path,
    artifact_id: str,
    fields: Mapping[str, Any],
    dry_run: bool,
) -> WriteResult | None:
    """The change recorded in place of this edit, or None where the artifact is this repository's own.

    The three edit functions ask this before doing anything else, so that a reference is recognised
    for what it is rather than by whatever their own resolution makes of it: `edit_document` resolves
    under `docs/`, where a reference never lives, and would have said the promoted document does not
    exist.
    """
    if registry is None:
        return None
    path = registry.find_file_by_id(artifact_id)
    if path is None or not path.exists():
        return None
    frontmatter = parse_frontmatter(path.read_text(encoding="utf-8")) or {}
    target = enterprise_target(frontmatter)
    if target is None:
        return None
    return _record_enterprise_change(
        kind=kind, repo=repo, registry=registry, verifier=verifier,
        clear_repo_caches=clear_repo_caches, repo_root=repo_root, reference_id=artifact_id,
        target_id=target, reference_frontmatter=frontmatter, fields=fields, dry_run=dry_run,
    )


def changes_under_submission(repo: "ArtifactRepository") -> frozenset[str]:
    """The changes a submission already in flight is carrying, or nothing where none is.

    A submission is recorded before its push, so a change can be committed to while still `draft`.
    An edit landing in that window supersedes rather than revises, and this is where the window is
    visible: the record lives on the *enterprise* repository's sync state, so an engagement
    deployment — which mounts none — correctly answers that nothing is in flight, because from here
    nothing is.
    """
    from src.infrastructure.git import enterprise_sync_state  # noqa: PLC0415

    enterprise = next((m.root for m in repo.repo_mounts if m.scope == "enterprise"), None)
    if enterprise is None:
        return frozenset()
    submission = enterprise_sync_state.load_cached(enterprise).submission
    return frozenset(submission.intent.proposal_ids) if submission is not None else frozenset()


def _record_enterprise_change(
    *,
    kind: ArtifactKind,
    repo: "ArtifactRepository | None",
    registry: "ArtifactRegistry",
    verifier: "ArtifactVerifier",
    clear_repo_caches: Callable[[Path], None],
    repo_root: Path,
    reference_id: str,
    target_id: str,
    reference_frontmatter: Mapping[str, Any],
    fields: Mapping[str, Any],
    dry_run: bool,
) -> WriteResult:
    """Record `fields` as a change against `target_id`, or say why it cannot be."""
    reference_path = registry.find_file_by_id(reference_id)
    name = _display_name(reference_frontmatter, reference_id)
    proxied = proxied_kind(reference_frontmatter)
    if proxied is None:
        return _refusal(
            reference_path, reference_id,
            f"'{name}' does not say which kind of enterprise artifact it stands for, so there is no "
            "vocabulary to record a change in.",
        )
    if proxied != kind:
        return _refusal(
            reference_path, reference_id,
            f"'{name}' stands for a {proxied}, and this is a {kind} edit. Edit it as a {proxied}: "
            f"a change records the fields a {proxied} has, and a {kind}'s are different.",
        )
    if not fields:
        return _refusal(reference_path, reference_id, "an edit that changes nothing is not a change")
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
        outcome = decide(
            kind=kind, target_id=target_id, fields=fields, pending=pending,
            under_submission=changes_under_submission(repo),
            baseline=current_values_of(repo.get_entity(target_id) or repo.get_document(target_id)),
        )
    except UnrecordableChange as refused:
        return _refusal(reference_path, reference_id, str(refused))

    return materialize(
        outcome,
        repo=repo,
        engagement_root=repo_root,
        verifier=verifier,
        clear_repo_caches=clear_repo_caches,
        target_name=name,
        reference_id=reference_id,
        # What the *enterprise artifact* is now — resolved through the one owner of that
        # question, because the standing compares the recorded value against it to decide staleness.
        # Hashing the reference file here instead made every change read stale from the moment it was
        # recorded, on any deployment that mounts the enterprise repository. The blank this used to
        # fall back to was refused by E148, so an engagement deployment — which mounts no enterprise
        # content and is where this feature is used — could record no change at all.
        base_revision=enterprise_revision(repo, target_id) or UNKNOWN_BASE,
        dry_run=dry_run,
    )


def _display_name(frontmatter: Mapping[str, Any], reference_id: str) -> str:
    name = frontmatter.get("name")
    return name if isinstance(name, str) and name.strip() else reference_id


def _refusal(path: Path | None, artifact_id: str, message: str) -> WriteResult:
    return WriteResult(
        wrote=False,
        path=path if path is not None else Path(artifact_id),
        artifact_id=artifact_id,
        content=None,
        warnings=[message],
        verification=None,
    )

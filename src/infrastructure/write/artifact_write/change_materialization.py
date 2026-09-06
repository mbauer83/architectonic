"""Putting a recorded change on disk, and taking the one it replaces out of the way.

`change_recording.decide` works out *what* a further edit does; this performs it. The two are apart
because the decision is a rule about lifecycles that must be statable against every combination
without a repository, and this is the half that needs one.

**A change is written the way the other system-managed artifact is.** A global artifact reference is
allocated an id, rendered by `format_entity_markdown`, verified, and removed again if the verifier
refuses it — so a repository never holds a file the product's own rules would reject. A change file
follows that exactly rather than growing its own spelling, and it is internal for the same reason:
the propose operation creates it and an author never authors one.

**Superseding writes the replacement before retiring what it replaces.** The order is the same one
`open_replacement_branch` keeps for the branch under review, and for the same reason: if the second
write fails, the author is left with their change rather than with neither. A terminal record is
retained rather than deleted — it is the evidence that the change existed and how it ended.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from src.application.modeling.change_recording import (
    ChangeOutcome,
    RecordNew,
    ReviseDraft,
    SupersedeSubmitted,
)
from src.application.modeling.proposal_edit import to_mapping
from src.application.modeling.proposed_change import (
    BASE_REVISION,
    PROPOSAL_STATE,
    PROPOSED_CHANGE_TYPE,
    PROPOSES_CHANGE_TO,
    RECORDED_EDIT,
)
from src.domain.ontology_representation.ontology_protocol import EntityTypeName
from src.infrastructure.write.artifact_write.proposal_lifecycle import mark_proposal_state
from src.infrastructure.write.artifact_write.types import WriteResult

if TYPE_CHECKING:
    from src.application.artifacts.query import ArtifactRepository
    from src.application.verification.artifact_verifier import ArtifactVerifier


def materialize(
    outcome: ChangeOutcome,
    *,
    repo: "ArtifactRepository",
    engagement_root: Path,
    verifier: "ArtifactVerifier",
    clear_repo_caches: Callable[[Path], None],
    target_name: str,
    reference_id: str,
    base_revision: str,
    dry_run: bool,
) -> WriteResult:
    """Perform `outcome`, returning what was written.

    `base_revision` is what the enterprise artifact is *now*, used only when a change is being
    recorded for the first time. Superseding carries the revision its predecessor was written
    against, which the outcome already holds — recomputing it here would silently mark a stale change
    current, which is the one thing the whole staleness contract must not do.
    """
    match outcome:
        case RecordNew(edit=edit):
            return _write_change(
                repo=repo, engagement_root=engagement_root, verifier=verifier,
                clear_repo_caches=clear_repo_caches, edit=edit, target_name=target_name,
                reference_id=reference_id, base_revision=base_revision, dry_run=dry_run,
            )
        case ReviseDraft(proposal_id=proposal_id, edit=edit):
            return _rewrite_recorded_edit(
                repo=repo, verifier=verifier, clear_repo_caches=clear_repo_caches,
                proposal_id=proposal_id, edit=edit, dry_run=dry_run,
            )
        case SupersedeSubmitted(superseded_ids=superseded, base_revision=carried, edit=edit):
            written = _write_change(
                repo=repo, engagement_root=engagement_root, verifier=verifier,
                clear_repo_caches=clear_repo_caches, edit=edit, target_name=target_name,
                reference_id=reference_id, base_revision=carried, dry_run=dry_run,
            )
            if written.wrote:
                # Only after the replacement exists. A failure between the two leaves the author
                # holding their change rather than neither of them.
                _retire(repo, superseded, clear_repo_caches=clear_repo_caches)
            return written


def _write_change(
    *,
    repo: "ArtifactRepository",
    engagement_root: Path,
    verifier: "ArtifactVerifier",
    clear_repo_caches: Callable[[Path], None],
    edit: object,
    target_name: str,
    reference_id: str,
    base_revision: str,
    dry_run: bool,
) -> WriteResult:
    from src.application.identifier_allocator import get_default_allocator  # noqa: PLC0415
    from src.application.modeling.artifact_write_formatting import (  # noqa: PLC0415
        format_entity_markdown,
    )
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415
    from src.infrastructure.write.artifact_write.boundary import modification_stamp  # noqa: PLC0415
    from src.infrastructure.write.artifact_write.entity import entity_path  # noqa: PLC0415

    recorded = to_mapping(edit)  # type: ignore[arg-type]
    info = get_module_registry().get_entity_type(EntityTypeName(PROPOSED_CHANGE_TYPE))
    change_id = get_default_allocator().allocate(prefix=info.prefix, name_hint=f"change to {target_name}")
    path = entity_path(engagement_root, info, change_id)

    content = format_entity_markdown(
        artifact_id=change_id,
        artifact_type=PROPOSED_CHANGE_TYPE,
        name=f"Change to {target_name}",
        version="0.1.0",
        status="active",
        last_updated=modification_stamp(),
        summary=f"A local change to `{recorded['artifact-id']}`, awaiting review.",
        properties=None,
        notes=None,
        # A change is internal and never drawn, so it carries no display section. Empty rather
        # than absent because the renderer takes both as required strings, and rendering this one
        # file another way would be a second spelling of the artifact format.
        display_section_id="",
        display_content="",
        repo_root=engagement_root,
        extra_frontmatter={
            # The *reference*, not what it stands for. A non-admin deployment holds no enterprise
            # content, so a change naming the enterprise artifact names something its own verifier
            # cannot find — E146, on the ordinary deployment. What the change is *against* is the
            # recorded edit's own `artifact-id`, which is not existence-checked because it is
            # resolved upstream, where the artifact lives.
            PROPOSES_CHANGE_TO: reference_id,
            PROPOSAL_STATE: "draft",
            BASE_REVISION: base_revision,
            RECORDED_EDIT: recorded,
        },
    )
    if dry_run:
        return WriteResult(wrote=False, path=path, artifact_id=change_id, content=content,
                           warnings=[], verification=None)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    result = verifier.verify_entity_file(path)
    if not result.valid:
        # The same rollback the reference creator performs: a repository never holds a file the
        # product's own verifier would refuse.
        path.unlink(missing_ok=True)
        return WriteResult(
            wrote=False, path=path, artifact_id=change_id, content=content, warnings=[],
            verification={
                "valid": False,
                "issues": [
                    {"severity": i.severity, "code": i.code, "message": i.message} for i in result.issues
                ],
            },
        )
    clear_repo_caches(path)
    return WriteResult(wrote=True, path=path, artifact_id=change_id, content=None,
                       warnings=[], verification=None)


def _rewrite_recorded_edit(
    *,
    repo: "ArtifactRepository",
    verifier: "ArtifactVerifier",
    clear_repo_caches: Callable[[Path], None],
    proposal_id: str,
    edit: object,
    dry_run: bool,
) -> WriteResult:
    """Replace a draft's recorded edit in place, keeping its identity and everything else about it."""
    import yaml  # type: ignore[import-untyped]  # noqa: PLC0415

    from src.domain.repository.frontmatter import (  # noqa: PLC0415
        parse_frontmatter,
        replace_frontmatter_text,
    )

    record = repo.get_entity(proposal_id)
    if record is None:
        raise ValueError(f"the change {proposal_id!r} it would revise is not in the repository")
    path = record.path
    source = path.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(source)
    if not frontmatter:
        raise ValueError(f"{proposal_id} has no frontmatter to revise")

    updated = {**frontmatter, RECORDED_EDIT: to_mapping(edit)}  # type: ignore[arg-type]
    dumped = yaml.safe_dump(updated, sort_keys=False)
    content = replace_frontmatter_text(source, str(dumped).strip())
    if dry_run:
        return WriteResult(wrote=False, path=path, artifact_id=proposal_id, content=content,
                           warnings=[], verification=None)

    previous = source
    path.write_text(content, encoding="utf-8")
    result = verifier.verify_entity_file(path)
    if not result.valid:
        path.write_text(previous, encoding="utf-8")
        return WriteResult(
            wrote=False, path=path, artifact_id=proposal_id, content=content, warnings=[],
            verification={
                "valid": False,
                "issues": [
                    {"severity": i.severity, "code": i.code, "message": i.message} for i in result.issues
                ],
            },
        )
    clear_repo_caches(path)
    return WriteResult(wrote=True, path=path, artifact_id=proposal_id, content=None,
                       warnings=[], verification=None)


def _retire(
    repo: "ArtifactRepository",
    superseded_ids: tuple[str, ...],
    *,
    clear_repo_caches: Callable[[Path], None],
) -> None:
    """Mark what was replaced terminal, retaining the record as the evidence it existed."""
    for proposal_id in superseded_ids:
        record = repo.get_entity(proposal_id)
        if record is None:
            continue
        if mark_proposal_state(record.path, artifact_id=proposal_id, state="abandoned"):
            clear_repo_caches(record.path)

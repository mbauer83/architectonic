"""Replace a library icon: re-point every diagram showing it at another icon, then delete it (D6).

An icon's picture never changes under its id (D1), so a new version of a logo is a new icon and this
is how its users move to it. The diagrams and the deletion are one transaction: a replacement that
re-pointed some diagrams and then failed would leave the old icon still shown and the new one half
adopted, and nothing reads that state as wrong.

Each diagram is rewritten by the diagram edit path, as a dry run, so its body is prepared, restated and
verified exactly as an author's edit would be; its embedded picture is keyed by digest and so moves with
it. The replacement is refused whole if any diagram would not verify, and while a specialization names
the icon as its default: specializations ship with the ontology, so this operation cannot re-point one.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from src.application.icons.effective_icons import with_icon_repointed
from src.application.icons.icon_usage import icon_users
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.domain.artifact_id import stable_id
from src.domain.icons.icon_ref import SharedIcon

from ._artifact_deduplication import get_repository
from .boundary import assert_engagement_write_root
from .diagram_edit import edit_diagram
from .diagram_render import render_diagram_outputs
from .file_transaction import FileChange, commit_file_changes
from .icon import IconInUseError, library_icon_here, refused_icon_write
from .types import WriteResult


def replace_icon(
    *,
    repo_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    artifact_id: str,
    replacement_id: str,
    dry_run: bool,
) -> WriteResult:
    """Re-point every diagram showing *artifact_id* at *replacement_id*, then delete *artifact_id*."""
    assert_engagement_write_root(repo_root)
    if verifier.registry is None:
        # Without one a kept body is not restated, and would go on showing the deleted picture.
        raise TypeError("replace_icon edits diagrams, so it needs a verifier with a registry")
    old = library_icon_here(repo_root, artifact_id)
    library = verifier.icon_library or get_repository(repo_root)
    new = library.get_icon(replacement_id)
    if new is None:
        raise FileNotFoundError(f"Icon '{replacement_id}' is in neither this library nor the enterprise's")
    if stable_id(new.artifact_id) == stable_id(old.artifact_id):
        raise ValueError("an icon cannot replace itself")
    repo = get_repository(repo_root)
    users = icon_users(old.artifact_id, repo.list_diagrams(), verifier.runtime_catalogs.specializations)
    if users.specializations:
        raise IconInUseError(
            f"{old.artifact_id} is the default of specializations {', '.join(users.specializations)}, "
            "which ship with the ontology and cannot be re-pointed here"
        )
    rewritten = [
        _rewritten_diagram(diagram_id, old.artifact_id, new.artifact_id, repo_root, verifier, clear_repo_caches)
        for diagram_id in users.diagrams
    ]
    refusals = [(result.artifact_id, _errors(result)) for result in rewritten if _errors(result)]
    if refusals:
        detail = "; ".join(f"{diagram}: {', '.join(errors)}" for diagram, errors in refusals)
        return refused_icon_write(old.path, old.artifact_id, f"re-pointing would leave diagrams invalid — {detail}")
    warnings = [f"Re-points {result.artifact_id} at {new.artifact_id}" for result in rewritten]
    if dry_run:
        return WriteResult(False, old.path, old.artifact_id, None, warnings, {"valid": True, "issues": []})
    changes = [FileChange(result.path, result.content) for result in rewritten]
    commit_file_changes(
        repo_root=repo_root, changes=[*changes, FileChange(old.path, None)],
        rebuild_index=lambda: None, label="icon-replace",
    )
    for change in changes:
        failures = render_diagram_outputs(change.path, warnings)
        warnings += [f"{change.path.name} did not render: {failure}" for failure in failures]
        clear_repo_caches(change.path)
    clear_repo_caches(old.path)
    return WriteResult(True, old.path, old.artifact_id, None, warnings, {"valid": True, "issues": []})


def _rewritten_diagram(
    diagram_id: str,
    old_id: str,
    new_id: str,
    repo_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
) -> WriteResult:
    diagram = get_repository(repo_root).get_diagram(diagram_id)
    if diagram is None or not diagram.path.is_relative_to(repo_root):
        raise IconInUseError(f"{old_id} is shown by {diagram_id}, which is not in this repository")
    raw = diagram.extra.get("diagram-entities")
    entities = with_icon_repointed(
        raw if isinstance(raw, Mapping) else {}, SharedIcon(stable_id(old_id)), SharedIcon(stable_id(new_id))
    )
    return edit_diagram(
        assert_write_root=assert_engagement_write_root, repo_root=repo_root, verifier=verifier,
        clear_repo_caches=clear_repo_caches, artifact_id=diagram_id, diagram_entities=entities, dry_run=True,
    )


def _errors(result: WriteResult) -> list[str]:
    issues = (result.verification or {}).get("issues", [])
    return [str(issue.get("message")) for issue in issues if issue.get("severity") == "error"]

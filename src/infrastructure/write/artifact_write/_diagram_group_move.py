"""Diagram-collection re-homing support: verify, write-or-move, relocate rendered outputs.

Split out of ``diagram_edit.py`` to keep that module's field-merging function
smaller. Shared by ``diagram_edit.edit_diagram`` (PUML diagrams) and
``matrix.create_matrix`` (matrix diagrams, via the ``verify_fn``/``render``
overrides) so both diagram kinds get the same verified move-or-write-in-place
and rollback semantics from one place.
"""

from collections.abc import Callable
from pathlib import Path

from src.application.document_links import relocated_links
from src.application.repo_path_helpers import (
    RENDERED_SUFFIXES,
    diagram_source_confidential_root,
    diagram_source_root,
    rendered_path_for,
)
from src.application.repository_confinement import path_inside
from src.application.verification.artifact_verifier import ArtifactVerifier, VerificationResult
from src.application.verification.artifact_verifier_types import Issue, Severity
from src.domain.repository.groups import UNCATEGORIZED

from .diagram_confidentiality import is_confidential_diagram_source
from .diagram_render import render_diagram_outputs
from .types import WriteResult
from .verify import verify_content_in_temp_path


def _verification_to_dict(path: Path, res) -> dict[str, object]:
    return {
        "path": str(path),
        "file_type": "diagram",
        "valid": res.valid,
        "issues": [
            {"severity": i.severity, "code": i.code, "message": i.message, "location": i.location} for i in res.issues
        ],
    }


def _resolve_diagram_group_path(
    *,
    repo_root: Path,
    current_path: Path,
    artifact_id: str,
    diagram_type: str,
    tlp: str | None,
    group: str | None,
) -> Path:
    """Return the diagram source path implied by re-homing to *group*.

    Returns *current_path* unchanged when ``group`` is None. Mirrors
    ``create_diagram``'s group-aware source-root selection (including the
    confidential-store redirect) so an edit-time move lands in the same place
    a fresh create with that group would have.
    """
    if group is None:
        return current_path
    diag_src_root = (
        diagram_source_confidential_root(repo_root)
        if is_confidential_diagram_source(diagram_type, tlp)
        else diagram_source_root(repo_root)
    )
    filename = f"{artifact_id}{current_path.suffix}"
    if group == UNCATEGORIZED:
        return path_inside(repo_root, diag_src_root, filename)
    return path_inside(repo_root, diag_src_root, group, filename)


def _relocate_rendered_outputs(old_diagram_path: Path, repo_root: Path) -> None:
    """Remove rendered PNG/SVG left behind at *old_diagram_path*'s location.

    Fresh outputs are re-rendered at the new location by the caller right
    after; this only clears the stale copies a group move would otherwise
    orphan under the old collection's rendered/ subdirectory.
    """
    for suffix in RENDERED_SUFFIXES:
        stale = rendered_path_for(old_diagram_path, repo_root, suffix)
        if stale.exists():
            stale.unlink()


def _carried_to_new_home(content: str, diagram_path: Path, target_path: Path) -> str:
    """*content* as it must read once an existing diagram has moved to *target_path*.

    Only a diagram whose notation is markdown carries prose links — a matrix body is a table of
    them — and a collection sits one directory deeper than the catalog root, so the links of a
    matrix moved between the two resolved one level out. A diagram being created has no old home
    to have been read from.
    """
    if target_path == diagram_path or target_path.suffix != ".md" or not diagram_path.exists():
        return content
    return relocated_links(
        content, read_from=diagram_path.parent, written_to=target_path.parent,
        moves={diagram_path: target_path},
    )


def _heal_links_to_moved_diagram(
    old_source: Path, new_source: Path, repo_root: Path, clear_repo_caches: Callable[[Path], None],
) -> list[str]:
    """Follow every link to the diagram's source and to its rendered images, and say which moved.

    A document shows a diagram by linking its rendered image and cites it by linking its source;
    both paths carry the collection, so both move. Only the source was followed, which left the
    picture missing from every document that showed it.
    """
    from ._entity_rename import rewrite_document_links_for_moved_artifact  # noqa: PLC0415

    moved_files = [
        (old_source, new_source),
        *(
            (rendered_path_for(old_source, repo_root, suffix), rendered_path_for(new_source, repo_root, suffix))
            for suffix in RENDERED_SUFFIXES
        ),
    ]
    healed = {
        linking_path
        for old_path, new_path in moved_files
        for linking_path in rewrite_document_links_for_moved_artifact(
            repo_root=repo_root, old_path=old_path, new_path=new_path
        )
    }
    for linking_path in healed:
        clear_repo_caches(linking_path)
    return [f"Updated document link in {linking_path.name}" for linking_path in sorted(healed)]


def commit_diagram_write(
    *,
    repo_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    artifact_id: str,
    diagram_path: Path,
    diagram_type: str,
    tlp: str | None,
    group: str | None,
    content: str,
    warnings: list[str],
    dry_run: bool,
    verify_fn: Callable[[Path], VerificationResult] | None = None,
    render: bool = True,
) -> WriteResult:
    """Verify *content*, then write it — relocating to *group*'s directory if given.

    ``verify_fn`` overrides the default ``verifier.verify_diagram_file`` — matrix
    diagrams pass ``verifier.verify_matrix_diagram_file`` instead, since their
    content is a markdown table, not PUML. ``render=False`` skips PNG/SVG
    generation for diagram kinds (matrix) that have no rendered image.
    """
    verify = verify_fn or verifier.verify_diagram_file
    target_path = _resolve_diagram_group_path(
        repo_root=repo_root, current_path=diagram_path, artifact_id=artifact_id,
        diagram_type=diagram_type, tlp=tlp, group=group,
    )
    moved = target_path != diagram_path
    content = _carried_to_new_home(content, diagram_path, target_path)

    if dry_run:
        res = verify_content_in_temp_path(
            verifier=verifier, file_type="diagram", desired_name=target_path.name,
            content=content, support_repo_root=repo_root, verify_fn=verify_fn,
        )
        if moved and diagram_path.exists():
            warnings.append(f"Will move diagram to group '{group}': {target_path}")
        return WriteResult(
            wrote=False, path=target_path, artifact_id=artifact_id, content=content,
            warnings=warnings, verification=_verification_to_dict(target_path, res),
        )

    write_path = target_path if moved else diagram_path
    prev = diagram_path.read_text(encoding="utf-8") if diagram_path.exists() else None
    write_path.parent.mkdir(parents=True, exist_ok=True)
    write_path.write_text(content, encoding="utf-8")

    res = verify(write_path)
    if not res.valid:
        if moved or prev is None:
            write_path.unlink()
        else:
            diagram_path.write_text(prev, encoding="utf-8")
        return WriteResult(
            wrote=False, path=write_path, artifact_id=artifact_id, content=content,
            warnings=warnings, verification=_verification_to_dict(write_path, res),
        )

    if moved and prev is not None:
        diagram_path.unlink()
        _relocate_rendered_outputs(diagram_path, repo_root)
        # A document citing this diagram links by path; the move breaks the link and nothing
        # else would say so.
        warnings.extend(_heal_links_to_moved_diagram(diagram_path, write_path, repo_root, clear_repo_caches))
        clear_repo_caches(diagram_path)
        warnings.append(f"Moved diagram to group '{group}': {write_path}")

    if render:
        res.issues.extend(
            Issue(Severity.ERROR, "E350", failure, str(write_path))
            for failure in render_diagram_outputs(write_path, warnings)
        )

    clear_repo_caches(write_path)
    return WriteResult(
        wrote=True, path=write_path, artifact_id=artifact_id, content=None,
        warnings=warnings, verification=_verification_to_dict(write_path, res),
    )

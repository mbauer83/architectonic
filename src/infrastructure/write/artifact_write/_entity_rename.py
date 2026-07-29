"""File-mechanics for renaming an entity's identity and moving its outgoing files."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from pathlib import Path

from src.application.document_links import MARKDOWN_LINK_RE, is_external_or_anchor_href
from src.application.repo_path_helpers import (
    all_model_roots,
    diagram_source_root,
    docs_root,
    rewrite_doc_link,
)
from src.domain.artifact_id import full_ids_with_stem, stable_id
from src.domain.repository.repo_layout import RENDERED


def rewrite_document_links_for_moved_entity(
    *, repo_root: Path, old_path: Path, new_path: Path
) -> list[Path]:
    """Rewrite markdown-body relative links that point at an entity's old path.

    Best-effort cosmetic update, mirroring the referrer rewrites for
    connection sidecars — entity moves (group re-home or rename) change the
    file's location, but nothing else updates a hand-authored `[label](../..
    /old/path.md)` link elsewhere in the docs tree.
    """
    changed: list[Path] = []
    doc_root = docs_root(repo_root)
    if not doc_root.exists():
        return changed
    for doc_path in doc_root.rglob("*.md"):
        text = doc_path.read_text(encoding="utf-8")

        def _replace(match: re.Match[str]) -> str:
            prefix, target, suffix = match.group(1), match.group(3), match.group(4)
            if is_external_or_anchor_href(target):
                return match.group(0)
            rewritten = rewrite_doc_link(
                target,
                doc_old_dir=doc_path.parent,
                doc_new_dir=doc_path.parent,
                target_old_path=old_path,
                target_new_path=new_path,
            )
            return f"{prefix}{rewritten}{suffix}" if rewritten != target else match.group(0)

        new_text = MARKDOWN_LINK_RE.sub(_replace, text)
        if new_text != text:
            doc_path.write_text(new_text, encoding="utf-8")
            changed.append(doc_path)
    return changed


def rename_entity_via_m4(
    *,
    entity_file: Path,
    target_entity_file: Path,
    new_content: str,
    repo_root: Path,
    artifact_id: str,
    effective_artifact_id: str,
    rebuild_index: Callable[[], None],
    on_boundary: Callable[[str], None] | None = None,
) -> list[Path]:
    """Commit an entity rename, its sidecar, AND every referring sidecar atomically via M4.

    Manifest: create new entity, create new sidecar, delete old entity, delete old sidecar,
    replace each outgoing file that references this entity.

    The referrer rewrites belong in this transaction rather than after it. Renaming is the
    only operation that invalidates a referrer's slug, so a rewrite that can be skipped —
    by a crash, an exception, or an early return — leaves the repository in a state nothing
    else repairs, and the drift is silent because the reference still resolves. Committing
    them together makes "the entity was renamed" and "its referrers name the new slug" a
    single fact.

    Returns [old_entity, new_entity, old_sidecar, new_sidecar, *referrers].
    """
    from src.infrastructure.write.artifact_write.file_transaction import (
        FileChange,
        commit_file_changes,
    )

    old_sidecar = entity_file.with_suffix(".outgoing.md")
    new_sidecar = target_entity_file.with_suffix(".outgoing.md")
    sidecar_content = old_sidecar.read_text(encoding="utf-8").replace(artifact_id, effective_artifact_id)

    # Planned before anything is staged, so a read failure aborts before any change lands.
    # The entity's own sidecar is excluded — it is already moving as part of this manifest.
    referrer_plan = plan_referrer_rewrites(
        repo_root=repo_root, new_artifact_id=effective_artifact_id, exclude_path=old_sidecar,
    )
    referrer_paths = sorted(referrer_plan)

    changes = [
        FileChange(path=target_entity_file, content=new_content),
        FileChange(path=entity_file, content=None),
        FileChange(path=new_sidecar, content=sidecar_content),
        FileChange(path=old_sidecar, content=None),
        *(FileChange(path=p, content=referrer_plan[p]) for p in referrer_paths),
    ]
    commit_file_changes(
        repo_root=repo_root, changes=changes, rebuild_index=rebuild_index,
        label="rename", on_boundary=on_boundary,
    )
    return [entity_file, target_entity_file, old_sidecar, new_sidecar, *referrer_paths]


def plan_referrer_rewrites(
    *,
    repo_root: Path,
    new_artifact_id: str,
    exclude_path: Path | None = None,
) -> dict[Path, str]:
    """Files referencing this entity under ANY slug, with their rewritten content.

    Covers both kinds of referrer: connection sidecars, which name the entity as a
    connection endpoint, and diagram sources, which name it in ``entity-ids-used`` and in
    composite connection ids. Both resolve leniently, so a stale slug in either is invisible
    at read time and only shows up as a reference no reader can interpret. Rendered output
    is excluded — it is regenerated from these sources.

    Matching is on the ``PREFIX@epoch.random`` stem rather than on the id the entity is
    being renamed *from*. Matching the old full id makes drift permanent: a referrer that
    was missed once holds some third slug, so no later rename can find it again, and the
    reference is stuck naming a title the entity has not had for a long time. Keyed on the
    stem, every referrer is found and healed no matter how stale it is.

    Returns a plan rather than writing, so the caller can commit these in the same M4
    transaction as the rename itself.
    """
    pattern = full_ids_with_stem(stable_id(new_artifact_id))
    plan: dict[Path, str] = {}
    for referrer_path in _referrer_sources(repo_root):
        if exclude_path is not None and referrer_path == exclude_path:
            continue
        text = referrer_path.read_text(encoding="utf-8")
        rewritten = pattern.sub(new_artifact_id, text)
        if rewritten != text:
            plan[referrer_path] = rewritten
    return plan


def _referrer_sources(repo_root: Path) -> Iterator[Path]:
    """Every authored file that can name an entity by id: sidecars and diagram sources."""
    for model_root in all_model_roots(repo_root):
        yield from model_root.rglob("*.outgoing.md")
    diagram_root = diagram_source_root(repo_root)
    if not diagram_root.exists():
        return
    rendered = (diagram_root.parent / RENDERED).resolve()
    for suffix in ("*.puml", "*.md"):
        for path in diagram_root.rglob(suffix):
            if not path.resolve().is_relative_to(rendered):
                yield path


def apply_referrer_rewrites(plan: dict[Path, str]) -> list[Path]:
    """Write a referrer plan directly, for the rename path that has no M4 transaction.

    Used only when the renamed entity has no outgoing sidecar of its own: there is no
    manifest to join, so the rewrites are applied here rather than skipped.
    """
    for outgoing_path, content in plan.items():
        outgoing_path.write_text(content, encoding="utf-8")
    return sorted(plan)


# ---------------------------------------------------------------------------
# Legacy helpers kept for the sidecar-less rename path in entity_edit.py
# ---------------------------------------------------------------------------


def rename_entity_identity(
    *,
    entity_file: Path,
    repo_root: Path,
    old_artifact_id: str,
    new_artifact_id: str,
) -> tuple[Path, list[Path]]:
    """Rewrite the entity's own outgoing file and every referrer from old id to new id."""
    new_entity_file = entity_file.with_name(f"{new_artifact_id}.md")

    old_outgoing = entity_file.with_suffix(".outgoing.md")
    new_outgoing = new_entity_file.with_suffix(".outgoing.md")
    changed_paths: list[Path] = []

    if old_outgoing.exists():
        outgoing_text = old_outgoing.read_text(encoding="utf-8").replace(old_artifact_id, new_artifact_id)
        new_outgoing.write_text(outgoing_text, encoding="utf-8")
        if new_outgoing != old_outgoing:
            old_outgoing.unlink()
        changed_paths.extend([old_outgoing, new_outgoing])

    for model_root in all_model_roots(repo_root):
        for outgoing_path in model_root.rglob("*.outgoing.md"):
            if outgoing_path == new_outgoing:
                continue
            text = outgoing_path.read_text(encoding="utf-8")
            if old_artifact_id not in text:
                continue
            outgoing_path.write_text(text.replace(old_artifact_id, new_artifact_id), encoding="utf-8")
            changed_paths.append(outgoing_path)

    return new_entity_file, changed_paths


def persist_rename(
    *, entity_file: Path, target_entity_file: Path, repo_root: Path, artifact_id: str, effective_artifact_id: str
) -> list[Path]:
    """Move the old entity file's identity to the new id, also relocating outgoing files on a group-move."""
    entity_file.unlink()
    _, renamed_paths = rename_entity_identity(
        entity_file=entity_file,
        repo_root=repo_root,
        old_artifact_id=artifact_id,
        new_artifact_id=effective_artifact_id,
    )
    if target_entity_file.parent != entity_file.parent:
        for outgoing_src in (
            entity_file.with_suffix(".outgoing.md"),
            entity_file.with_name(f"{effective_artifact_id}.outgoing.md"),
        ):
            if outgoing_src.exists():
                new_outgoing = target_entity_file.with_suffix(".outgoing.md")
                new_outgoing.parent.mkdir(parents=True, exist_ok=True)
                outgoing_src.rename(new_outgoing)
                renamed_paths.extend([outgoing_src, new_outgoing])
                break
    return renamed_paths

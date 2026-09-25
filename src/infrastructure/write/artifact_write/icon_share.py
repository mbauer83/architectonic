"""Share an icon a diagram holds for itself: add it to the library and have the diagram name it there (D11).

The picture the diagram stores is already the normalised one, so it is the upload; the icon then goes
through the library's own create path, applicability and attribution checks included. A picture the
library already holds is not added twice — the diagram is pointed at that icon instead.

The library icon is written before the diagram is changed, because the diagram's edit is verified
against the library and must find the icon there. If the edit is then refused, the icon is deleted
again. A crash between the two leaves an icon nothing uses yet, which the library shows and can
delete; it never leaves a diagram naming an icon that does not exist. The diagram's own copy is dropped
by that edit, as every unused ad-hoc icon is.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from src.application.artifacts.icon_parsing import parse_icon
from src.application.icons.effective_icons import LOCAL_ICONS_KEY, with_icon_repointed
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.verifier_ports import IconLibrary
from src.domain.artifact_id import stable_id
from src.domain.icons.icon_record import IconRecord
from src.domain.icons.icon_ref import LocalIcon, icon_target_from
from src.infrastructure.icons.diagram_icons import DiagramIconSource

from ._artifact_deduplication import get_repository
from .boundary import assert_engagement_write_root
from .diagram_edit import edit_diagram
from .icon import IconUpload, create_icon, library_icon_with_digest, refused_icon_write
from .types import WriteResult


def share_icon(
    *,
    repo_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    diagram_id: str,
    icon_key: str,
    attribution: str,
    tags: Sequence[str] = (),
    dry_run: bool,
) -> WriteResult:
    """Add the diagram's `local:<icon_key>` to the library and re-point the diagram at it."""
    assert_engagement_write_root(repo_root)
    if verifier.registry is None:
        # Without one a kept body is not restated, and would go on showing the diagram's own copy.
        raise TypeError("share_icon edits a diagram, so it needs a verifier with a registry")
    diagram = get_repository(repo_root).get_diagram(diagram_id)
    if diagram is None or not diagram.path.is_relative_to(repo_root):
        raise FileNotFoundError(f"Diagram '{diagram_id}' is not in this repository")
    raw = diagram.extra.get("diagram-entities")
    entities: Mapping[str, object] = raw if isinstance(raw, Mapping) else {}
    local = DiagramIconSource(entities, None)(LocalIcon(icon_key))
    if local is None:
        raise FileNotFoundError(f"Diagram '{diagram_id}' holds no icon of its own under '{icon_key}'")

    held = library_icon_with_digest(repo_root, local.render_digest)
    if held is not None:
        return _pointed_at(held, entities, icon_key, diagram.artifact_id, repo_root, verifier, clear_repo_caches,
                           dry_run=dry_run, warnings=[f"The library already holds this picture as {held}"])
    upload = IconUpload(
        content=local.png, source_format="png", name=_local_name(entities, icon_key), attribution=attribution,
        applies_to=local.applies_to.as_list(), default_style=local.default_style, tags=tuple(tags),
    )
    created = create_icon(
        repo_root=repo_root, verifier=verifier, clear_repo_caches=clear_repo_caches, upload=upload, dry_run=dry_run,
    )
    if dry_run or not created.wrote:
        return created
    # The index may not have been told of the icon yet; the diagram's edit resolves it all the same.
    library = _WithIcon(verifier.icon_library, created.path)
    shared = _pointed_at(created.artifact_id, entities, icon_key, diagram.artifact_id, repo_root,
                         verifier.with_icon_library(library), clear_repo_caches, dry_run=False, warnings=[])
    if not shared.wrote:
        created.path.unlink(missing_ok=True)
        clear_repo_caches(created.path)
    return shared


def _pointed_at(
    icon_id: str,
    entities: Mapping[str, object],
    icon_key: str,
    diagram_id: str,
    repo_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    *,
    dry_run: bool,
    warnings: list[str],
) -> WriteResult:
    repointed = with_icon_repointed(entities, LocalIcon(icon_key), icon_target_from(icon_id))
    edited = edit_diagram(
        assert_write_root=assert_engagement_write_root, repo_root=repo_root, verifier=verifier,
        clear_repo_caches=clear_repo_caches, artifact_id=diagram_id, diagram_entities=repointed, dry_run=dry_run,
    )
    if edited.error_messages:
        return refused_icon_write(edited.path, icon_id, "; ".join(edited.error_messages))
    return WriteResult(edited.wrote, edited.path, icon_id, edited.content, [*warnings, *edited.warnings],
                       edited.verification)


class _WithIcon:
    """A library that also holds the icon just written at *path*."""

    def __init__(self, base: IconLibrary | None, path: Path) -> None:
        self._base = base
        self._added = parse_icon(path)

    def get_icon(self, artifact_id: str) -> IconRecord | None:
        if self._added is not None and stable_id(artifact_id) == stable_id(self._added.artifact_id):
            return self._added
        return self._base.get_icon(artifact_id) if self._base is not None else None


def _local_name(entities: Mapping[str, object], icon_key: str) -> str:
    own = entities.get(LOCAL_ICONS_KEY)
    entry = own.get(icon_key) if isinstance(own, Mapping) else None
    name = entry.get("name") if isinstance(entry, Mapping) else None
    return str(name) if name else icon_key

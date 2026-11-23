"""Patch part of a diagram's layout: the entries an editor or an agent changed, applied to the one stored.

The write is the diagram edit's own (`edit_diagram(layout=…)`), so a patched layout is refused, pruned
and verified exactly as a whole block is. What is decided here is only what the patch applies *to*:

* the stored layout, where the diagram has one;
* otherwise the first layout — PlantUML's picture written down with its narrow gaps widened, once.
  A diagram is taken over from exactly the picture it had, so a patch that moves one element of an
  automatically laid-out diagram leaves every other element where it was drawn.

A patch whose entries moved under it (`LayoutConflict`) applies nothing. A caller that states intents
rather than entries passes a function that compiles the patch from that same base and the stored layout
(`layout_intents.compiled_patch`), so the base is chosen here once for both.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from src.application.repo_path_helpers import resolve_diagram_source_path
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.domain.diagrams.layout.layout_block import LAYOUT_KEY, Layout, layout_as_written, read_layout
from src.domain.diagrams.layout.layout_checks import DiagramIdentities, pruned_to
from src.domain.diagrams.layout.layout_patch import patched, read_layout_patch

from .diagram_edit import edit_diagram
from .parse_existing import parse_diagram_file
from .types import WriteResult

#: The layout a diagram starts from when it has none: from its body and frontmatter.
type FirstLayout = Callable[[str, Mapping[str, object]], Layout]

#: A patch compiled from the base the diagram is arranged by and the layout it stores.
type PatchOf = Callable[[Layout, Layout], Mapping[str, object]]


@dataclass(frozen=True)
class LayoutPatchResult:
    """The diagram write, the layout block the diagram holds after it (empty: none), and the patch applied."""

    write: WriteResult
    layout: dict[str, object]
    patch: Mapping[str, object]


def reconciled_layout(
    *, stored: object, patch: Mapping[str, object], identities: DiagramIdentities,
    place_members: Callable[[Layout], Layout] | None = None,
) -> dict[str, object]:
    """The layout a diagram write stores when what the diagram holds changes in the same write (D12).

    The stored layout with the editor's patch applied — each entry checked against what the editor read —
    less every entry naming what the diagram no longer holds: placed instances keep their places, removed
    ones and their routes go. Unstated boxes are fitted round their members when the picture is composed.
    Raises `LayoutConflict` or `MalformedLayout` (a ValueError) for a patch that cannot apply.
    """
    base = read_layout(stored) if isinstance(stored, Mapping) and stored else Layout()
    kept, _dropped = pruned_to(patched(base, read_layout_patch(patch), stored=base), identities)
    if place_members is not None and not kept.states_nothing():
        kept = place_members(kept)
    return layout_as_written(kept)


def patch_diagram_layout(
    *,
    repo_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    assert_write_root: Callable[[Path], None],
    artifact_id: str,
    patch: Mapping[str, object] | PatchOf,
    first_layout: FirstLayout,
    dry_run: bool,
) -> LayoutPatchResult:
    """Apply *patch* — stated, or compiled from the base — to *artifact_id*'s layout and write it.

    Raises ValueError for a refused patch.
    """
    find = verifier.registry.find_file_by_id if verifier.registry is not None else None
    diagram_path = resolve_diagram_source_path(repo_root, artifact_id, find)
    if diagram_path is None:
        raise ValueError(f"Diagram '{artifact_id}' not found")
    parsed = parse_diagram_file(diagram_path)
    raw = parsed.frontmatter.get(LAYOUT_KEY)
    stored = read_layout(raw) if isinstance(raw, Mapping) and raw else Layout()
    base = stored if not stored.states_nothing() else first_layout(parsed.puml_body, parsed.frontmatter)
    stated = patch(base, stored) if callable(patch) else patch
    block = layout_as_written(patched(base, read_layout_patch(stated), stored=stored))
    write = edit_diagram(
        assert_write_root=assert_write_root, repo_root=repo_root, verifier=verifier,
        clear_repo_caches=clear_repo_caches, artifact_id=artifact_id, layout=block, dry_run=dry_run,
    )
    return LayoutPatchResult(write=write, layout=block, patch=stated)

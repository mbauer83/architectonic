"""Move rendered output left behind under a collection's former slug.

A diagram collection is backed by more than its source directory. The PUML sits under
``diagram-catalog/diagrams/<slug>/``; the PNG and SVG it renders to sit under
``diagram-catalog/rendered/<slug>/``, filed by the source's own collection segment. Renaming the
collection used to move the first and leave the second, so the sources took the new slug and their
rendered output kept the old one.

Nothing reported it. The SVG route re-derives on read and went on answering 200, while the PNG
download — which serves the file on disk — answered ``404 PNG not yet rendered — save the diagram
first`` for every diagram in the collection. A reader who asked for a picture got a refusal naming a
save they had already done. Measured in this repository months after the rename, while re-shooting
the documentation media.

The rename itself is fixed (``_group_fs._diagram_collection_dirs`` now names every directory a
collection is filed under). This heals repositories the old one already moved, and it derives the
destination from where each diagram's source sits *now* rather than from any record of the rename —
so it repairs output stranded by a rename nobody recorded, and repairs it however many renames ago
it happened.

Confidential renderings are not in scope and must not be: they land in ``rendered/confidential/``
flat, with no slug segment, so a collection rename never strands them.
"""

from __future__ import annotations

from pathlib import Path

from src.application.repo_path_helpers import (
    RENDERED_SUFFIXES,
    diagram_source_root,
    rendered_dir_for_diagram,
    rendered_root,
)
from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding


def _sources_by_stem(view: RepoUpgradeView) -> dict[str, str]:
    """Diagram stem → its source file's path, relative to the repo root.

    A stem naming more than one source is left out: there is no single place its rendering
    belongs, and guessing would file a picture under the wrong collection.
    """
    root = diagram_source_root(view.root)
    try:
        pattern = f"{root.relative_to(view.root).as_posix()}/**/*"
    except ValueError:  # pragma: no cover - a repo whose catalog is outside its own root
        return {}
    found: dict[str, str | None] = {}
    for relative in view.list_files(pattern):
        stem = Path(relative).stem
        found[stem] = None if stem in found else relative
    return {stem: path for stem, path in found.items() if path is not None}


def _misfiled(view: RepoUpgradeView) -> list[tuple[str, str]]:
    """Every rendered file whose directory is not the one its source implies, as (from, to)."""
    rendered = rendered_root(view.root)
    try:
        pattern = f"{rendered.relative_to(view.root).as_posix()}/**/*"
    except ValueError:  # pragma: no cover - as above
        return []
    sources = _sources_by_stem(view)

    moves: list[tuple[str, str]] = []
    for relative in view.list_files(pattern):
        current = Path(relative)
        if current.suffix not in RENDERED_SUFFIXES:
            continue
        source = sources.get(current.stem)
        if source is None:
            # No source with this stem: the diagram was deleted, or predates this layout. Either
            # way there is nowhere to file the picture, and removing it is not this step's call.
            continue
        belongs = rendered_dir_for_diagram(view.root / source, view.root) / current.name
        destination = belongs.relative_to(view.root).as_posix()
        if destination != relative:
            moves.append((relative, destination))
    return moves


class RenderedOutputCollectionStep:
    id = "d11-rendered-output-under-a-former-slug"
    version = 1
    description = "Move rendered diagram output filed under a collection's former slug"
    scanned_surface: ScannedSurface = "rendered_output"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        return [
            UpgradeFinding(
                step_id=self.id,
                finding_id=f"{self.id}:{source}",
                location=source,
                description=(
                    f"Rendered output sits in {Path(source).parent.as_posix()!r}; its diagram's "
                    f"collection files it in {Path(destination).parent.as_posix()!r}, and the PNG "
                    "download answers 404 for it where it is."
                ),
                severity="warning",
                auto_migratable=True,
                rewrite_summary=f"Move to {destination}",
            )
            for source, destination in _misfiled(view)
        ]

    def apply(
        self,
        view: RepoUpgradeView,
        writer: RepoUpgradeWriter,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        # Where each file belongs is re-derived rather than read off the finding, so a re-run
        # after a partial apply moves what is still misfiled and leaves the rest alone.
        destinations = dict(_misfiled(view))
        applied: list[AppliedFinding] = []
        for finding in findings:
            destination = destinations.get(finding.location)
            if destination is None:
                applied.append(
                    AppliedFinding(finding=finding, outcome="skipped", detail="Already filed correctly")
                )
                continue
            writer.move_file(finding.location, destination)
            applied.append(AppliedFinding(finding=finding, outcome="applied"))
        return applied

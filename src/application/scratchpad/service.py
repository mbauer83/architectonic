"""The one service both surfaces drive.

Parity between MCP and REST is a *property of this feature* rather than of the platform — the
platform principle explicitly disclaims full parity across every surface, and the scratchpad has a
local reason it does not: it is the lowest-barrier surface, so a human-only version would make the
one place newcomers start the one place agents cannot help.

Parity is easy to claim and hard to keep, so it is arranged rather than promised. Every capability
is a method here; the REST router and the MCP tools are both thin adapters over these methods and
neither may reach past them. A capability that exists on one surface and not the other is then a
missing *adapter*, which a test can see — `tests/architecture/test_scratchpad_surface_parity.py`
compares the two against this class.
"""

from __future__ import annotations

from dataclasses import replace

from src.application.scratchpad.ports import (
    ScratchpadRepositoryPort,
    ScratchpadSummary,
)
from src.domain.scratchpad import (
    Area,
    Layout,
    Link,
    Note,
    Point,
    Rect,
    Scratchpad,
    ScratchpadError,
    scratchpad_from_parts,
)

#: The four areas a new scratchpad is seeded with, and what each is for. Defaults rather than a
#: fixed structure: a scratchpad may add, rename or remove areas, and the permitted-type sets that
#: turn these into a narrowing arrive with typing (slice 3).
DEFAULT_AREAS: tuple[tuple[str, str], ...] = (
    ("strategy", "Vision & strategy"),
    ("portfolio", "Portfolio"),
    ("project", "Project"),
    ("enabling", "Enabling"),
)

#: Where the seeded frames sit. Stacked rather than tiled, because a cross-area link is the content
#: worth having and a vertical stack keeps every such link short and legible.
_AREA_WIDTH, _AREA_HEIGHT, _AREA_GAP = 1200, 600, 40


class ScratchpadService:
    """Aggregate operations. Holds no HTTP, no MCP, and no rendering concerns."""

    def __init__(self, repository: ScratchpadRepositoryPort) -> None:
        self._repository = repository

    # ── Reads ────────────────────────────────────────────────────────────────

    def list_scratchpads(
        self, *, group: str | None = None, status: str | None = None
    ) -> list[ScratchpadSummary]:
        return self._repository.list_scratchpads(group=group, status=status)

    def read(self, artifact_id: str) -> Scratchpad:
        return self._repository.load(artifact_id)

    # ── Writes ───────────────────────────────────────────────────────────────

    def create(
        self,
        *,
        artifact_id: str,
        name: str,
        group: str,
        description: str = "",
        meta_ontology: str = "archimate-4",
        seed_areas: bool = True,
    ) -> Scratchpad:
        """A new scratchpad, seeded with the four areas unless asked otherwise.

        Seeded by default because an empty canvas answers none of "what goes where", and the four
        areas are the vocabulary the feature is designed around. `seed_areas=False` exists for the
        caller who wants their own — an agent restoring an export, most obviously.
        """
        areas = [Area(id=area_id, label=label) for area_id, label in DEFAULT_AREAS] if seed_areas else []
        layout = Layout(areas={
            area_id: _area_rect(index) for index, (area_id, _) in enumerate(DEFAULT_AREAS)
        }) if seed_areas else Layout()
        scratchpad = scratchpad_from_parts(
            artifact_id=artifact_id,
            name=name,
            description=description,
            meta_ontology=meta_ontology,
            areas=areas,
            layout=layout,
        )
        return self._repository.save(scratchpad, group=group, expected_version=None)

    def replace(self, scratchpad: Scratchpad, *, group: str, expected_version: str) -> Scratchpad:
        """Write the aggregate whole.

        Whole rather than by part because the root enforces the invariants: a partial update cannot
        be validated without loading everything anyway, and one shape removes the class of bug where
        two partial updates interleave into a state neither writer intended.
        """
        scratchpad.validate()
        return self._repository.save(scratchpad, group=group, expected_version=expected_version)

    def delete(self, artifact_id: str) -> None:
        self._repository.delete(artifact_id)

    # ── Convenience the canvas does NOT use, and the agent surface does ───────
    #
    # The canvas mutates its in-memory aggregate and saves whole (that is what keeps it to one
    # write a second). An agent has no canvas, so it needs to say "add this note" without
    # reconstructing the document — these compose to the same `replace`, so neither surface has a
    # path into storage the other lacks.

    def add_note(
        self, artifact_id: str, *, note_id: str, title: str, at: Point | None = None, body: str = ""
    ) -> Scratchpad:
        current = self._repository.load(artifact_id)
        if current.note(note_id) is not None:
            raise ScratchpadError(f"note {note_id!r} already exists in {artifact_id!r}")
        updated = current.with_note(Note(id=note_id, title=title, body=body), at=at)
        return self.replace(updated, group=self._group_of(artifact_id), expected_version=current.version)

    def move_note(self, artifact_id: str, *, note_id: str, to: Point) -> Scratchpad:
        current = self._repository.load(artifact_id)
        updated = current.moved(note_id, to)
        return self.replace(updated, group=self._group_of(artifact_id), expected_version=current.version)

    def remove_note(self, artifact_id: str, *, note_id: str) -> Scratchpad:
        current = self._repository.load(artifact_id)
        updated = current.without_note(note_id)
        return self.replace(updated, group=self._group_of(artifact_id), expected_version=current.version)

    def add_link(self, artifact_id: str, *, link_id: str, source: str, target: str) -> Scratchpad:
        current = self._repository.load(artifact_id)
        if any(link.id == link_id for link in current.links):
            raise ScratchpadError(f"link {link_id!r} already exists in {artifact_id!r}")
        updated = current.with_link(Link(id=link_id, source=source, target=target))
        return self.replace(updated, group=self._group_of(artifact_id), expected_version=current.version)

    def remove_link(self, artifact_id: str, *, link_id: str) -> Scratchpad:
        current = self._repository.load(artifact_id)
        updated = current.without_link(link_id)
        return self.replace(updated, group=self._group_of(artifact_id), expected_version=current.version)

    def rename_note(self, artifact_id: str, *, note_id: str, title: str) -> Scratchpad:
        current = self._repository.load(artifact_id)
        note = current.note(note_id)
        if note is None:
            raise ScratchpadError(f"no note {note_id!r} in {artifact_id!r}")
        updated = current.with_note(replace(note, title=title))
        return self.replace(updated, group=self._group_of(artifact_id), expected_version=current.version)

    def _group_of(self, artifact_id: str) -> str:
        """The collection an edit must save back into — asked of the port, which declares it."""
        return self._repository.group_of(artifact_id)


def _area_rect(index: int) -> Rect:
    return Rect(0, index * (_AREA_HEIGHT + _AREA_GAP), _AREA_WIDTH, _AREA_HEIGHT)

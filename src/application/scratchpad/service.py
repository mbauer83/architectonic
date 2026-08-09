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

from src.application.scratchpad.lift import (
    LiftPlan,
    LiftReceipt,
    plan_lift,
    verdict_source,
)
from src.application.scratchpad.ports import (
    LiftWriterPort,
    ScratchpadRepositoryPort,
    ScratchpadSummary,
)
from src.domain.modules.module_registry import ModuleRegistry
from src.domain.scratchpad import (
    Area,
    Layout,
    Link,
    ModelRef,
    Note,
    Rect,
    Scratchpad,
    scratchpad_from_parts,
)

#: The four areas a new scratchpad is seeded with, what each is for, and which domains it holds.
#:
#: The frames are **work archetypes**, not layers, which is why only the first narrows: vision and
#: strategy work is motivation and strategy by definition, while portfolio, project and enabling
#: work each reach across the whole model — a project produces application components and business
#: processes as readily as requirements. Narrowing those would be inventing a rule the work does not
#: have.
#:
#: Defaults rather than a fixed structure: a scratchpad may add, rename or remove areas, and may
#: widen or narrow any of them.
DEFAULT_AREAS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("strategy", "Vision & strategy", ("motivation", "strategy")),
    ("portfolio", "Portfolio", ()),
    ("project", "Project", ()),
    ("enabling", "Enabling", ()),
)

#: Where the seeded frames sit. Stacked rather than tiled, because a cross-area link is the content
#: worth having and a vertical stack keeps every such link short and legible.
_AREA_WIDTH, _AREA_HEIGHT, _AREA_GAP = 1200, 600, 40


class ScratchpadService:
    """Aggregate operations. Holds no HTTP, no MCP, and no rendering concerns."""

    def __init__(
        self,
        repository: ScratchpadRepositoryPort,
        registry: ModuleRegistry,
        lift_writer: LiftWriterPort,
    ) -> None:
        self._repository = repository
        self._registry = registry
        self._lift_writer = lift_writer

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
        areas = [
            Area(id=area_id, label=label, permitted_domains=domains)
            for area_id, label, domains in DEFAULT_AREAS
        ] if seed_areas else []
        layout = Layout(areas={
            area_id: _area_rect(index) for index, (area_id, *_rest) in enumerate(DEFAULT_AREAS)
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

    def group_of(self, artifact_id: str) -> str:
        """Which collection this scratchpad sits in — needed to save an edit back into it."""
        return self._repository.group_of(artifact_id)

    def lift(
        self,
        artifact_id: str,
        *,
        selection: list[str],
        targets: dict[str, str],
        expected_version: str,
        draw: bool = False,
        dry_run: bool = True,
    ) -> tuple[LiftPlan, LiftReceipt]:
        """Preflight a lift, and perform it unless asked only to plan.

        *targets* maps a frame's id to the project its content lands in — one target per frame,
        because the frames are work archetypes and a canvas routinely holds work for more than one
        project. A frame with no entry lands in the root model.

        Planning and performing are one operation on one route, as the write tools already are: a
        plan that cannot be executed by the same call is a plan someone has to trust twice, and the
        second call would be made against a scratchpad that may have moved on.

        A blocked plan performs nothing and says why. So does `dry_run`, which is the default —
        every write on this surface plans unless told otherwise.
        """
        scratchpad = self._repository.load(artifact_id)
        plan = plan_lift(
            scratchpad,
            selection=selection,
            targets={
                area: self._lift_writer.resolve_target(group) for area, group in targets.items()
            },
            verdict_of=verdict_source(self._registry, scratchpad),
            draw=draw,
        )
        if dry_run or plan.blocks or plan.is_empty:
            return plan, LiftReceipt()

        receipt = self._lift_writer.execute(
            plan, meta_ontology=scratchpad.meta_ontology, dry_run=False
        )
        if receipt.committed:
            # The *scratchpad* records what the lift created; the model is never written back to.
            # This is the one edge a lift adds to the aggregate, and it is what makes a second lift
            # skip rather than duplicate.
            self._repository.save(
                _realized(scratchpad, receipt.realized),
                group=self._repository.group_of(artifact_id),
                expected_version=expected_version,
            )
        return plan, receipt



def _realized(scratchpad: Scratchpad, allocated: dict[str, str]) -> Scratchpad:
    """The same scratchpad, with every note and link the lift created pointing at what it became.

    `realized` rather than `bound`: the distinction is provenance, and it is what decides whether
    untyping is free. A realized note may only be *forgotten*, because a model entity depends on
    the type it was lifted with.
    """
    def realized_note(note: Note) -> Note:
        created = allocated.get(note.id)
        return replace(note, model_ref=ModelRef(created, "realized")) if created else note

    def realized_link(link: Link) -> Link:
        created = allocated.get(link.id)
        return replace(link, model_ref=ModelRef(created, "realized")) if created else link

    return replace(
        scratchpad,
        notes=tuple(realized_note(note) for note in scratchpad.notes),
        links=tuple(realized_link(link) for link in scratchpad.links),
    )


def _area_rect(index: int) -> Rect:
    return Rect(0, index * (_AREA_HEIGHT + _AREA_GAP), _AREA_WIDTH, _AREA_HEIGHT)

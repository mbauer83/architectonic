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

from src.application.scratchpad.edit import ScratchpadEdit, apply_edit
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
from src.domain.repository.groups import UNCATEGORIZED
from src.domain.scratchpad import (
    Area,
    Layout,
    Link,
    ModelRef,
    Note,
    Rect,
    Scratchpad,
    refuse_forbidden_transitions,
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
        group: str = UNCATEGORIZED,
        description: str = "",
        meta_ontology: str = "archimate-4",
        seed_areas: bool = True,
    ) -> Scratchpad:
        """A new scratchpad, seeded with the four areas unless asked otherwise.

        Seeded by default because an empty canvas answers none of "what goes where", and the four
        areas are the vocabulary the feature is designed around. `seed_areas=False` exists for the
        caller who wants their own — an agent restoring an export, most obviously.

        `group` is a **folder**, and it defaults, because a scratchpad is free-standing. It used to
        be required and drawn from the model-project axis, which asked at the worst possible moment
        for the one answer a scratchpad is designed not to need: a lift chooses a target *per frame*,
        so the thinking that spans projects — the material worth having — had to be filed under one
        of them before a word of it was written.
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

        A whole document says what the scratchpad should *be*, and the aggregate also has rules
        about what it may *stop being* — a realized note is not retyped, the meta-ontology does not
        change under typed notes. Those are asked here, of the stored scratchpad against the
        submitted one, so they hold for every write rather than only for a caller of the mutation
        that states them.
        """
        self._repository.require_version(scratchpad.artifact_id, expected_version)
        return self._written(
            self._repository.load(scratchpad.artifact_id), scratchpad,
            group=group, expected_version=expected_version,
        )

    def edit(
        self, artifact_id: str, *, edit: ScratchpadEdit, expected_version: str
    ) -> Scratchpad:
        """The same write as `replace`, addressed by what changed.

        Added because `replace` puts the cost of the smallest edit on the size of the canvas: an
        agent removing one note had to read the whole document and send it all back. This is not a
        second door into storage — the delta becomes an aggregate and takes the identical path, so
        the invariants, the refusals and the version token are the same code, not the same intent.
        """
        self._repository.require_version(artifact_id, expected_version)
        stored = self._repository.load(artifact_id)
        return self._written(
            stored, apply_edit(stored, edit),
            group=self._repository.group_of(artifact_id), expected_version=expected_version,
        )

    def _written(
        self, stored: Scratchpad, submitted: Scratchpad, *, group: str, expected_version: str
    ) -> Scratchpad:
        """The one write both shapes end in: the transition is permitted, the result holds."""
        refuse_forbidden_transitions(stored, submitted)
        submitted.validate()
        return self._repository.save(submitted, group=group, expected_version=expected_version)

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

        **The version is asked for before the model is written, not after.** A lift writes twice —
        the model, then the scratchpad that records what each note became — and only the second
        write used to check the token. A stale caller got the content committed, then a conflict,
        and notes that did not say they had been lifted, so the retry the conflict asks for created
        everything again.
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

        self._repository.require_version(artifact_id, expected_version)
        _recordable(scratchpad, plan)
        receipt = self._lift_writer.execute(
            plan, meta_ontology=scratchpad.meta_ontology, dry_run=False
        )
        if not receipt.committed:
            return plan, receipt
        return plan, self._recorded(scratchpad, receipt, expected_version=expected_version)

    def _recorded(
        self, scratchpad: Scratchpad, receipt: LiftReceipt, *, expected_version: str
    ) -> LiftReceipt:
        """The receipt, once the scratchpad says what the lift created.

        The *scratchpad* records it; the model is never written back to. This is the one edge a
        lift adds to the aggregate, and it is what makes a second lift skip rather than duplicate.

        The model write has committed by now and cannot be taken back, so a failure here is
        *reported on the receipt* rather than raised: an exception would tell the caller the lift
        failed, and the retry that invites is the duplicate. The receipt still says `committed` and
        still carries every id, which is everything needed to bind the notes by hand. That holds
        for *any* failure, not only the ones this was written expecting: a refusal by the aggregate
        once escaped here as an exception, and a lift that had written a document answered
        `refused`.
        """
        try:
            self._repository.save(
                _realized(scratchpad, receipt.realized),
                group=self._repository.group_of(scratchpad.artifact_id),
                expected_version=expected_version,
            )
        except Exception as exc:  # noqa: BLE001 — whatever failed, the model write stands; see above
            return replace(receipt, errors=(*receipt.errors, _unrecorded(exc)))
        return receipt


def _recordable(scratchpad: Scratchpad, plan: LiftPlan) -> None:
    """Refuse a lift whose outcome the scratchpad could not record, before anything is written.

    Asked of the aggregate itself, by building the scratchpad the lift would leave behind and
    validating it. The alternative is to learn it after the model write has committed, when the only
    honest answer left is "it is written, and nothing here says so" — and the retry that invites
    writes it again. Raises `ScratchpadError`, the refusal every other write on this surface gives.
    """
    pending = {item.id: f"pending:{item.id}" for item in plan.of("create")}
    _realized(scratchpad, pending).validate()


def _unrecorded(cause: Exception) -> str:
    return (
        "The content was written to the model, but the scratchpad could not be updated to record "
        f"it ({cause}). Do not lift these notes again — that would create the content a second "
        "time. Reload the scratchpad and set each note's model-ref to the id listed for it under "
        "`realized`."
    )



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

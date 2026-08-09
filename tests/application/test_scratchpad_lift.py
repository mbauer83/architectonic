"""The preflight, which is where a lift is decided.

Every case here runs without a repository, a registry or a write path — that is the whole reason
planning is a pure function over the aggregate and a verdict callable. It is also why there are so
many cases: this is the payload a person reads immediately before turning a sketch into model
content, and each row of it is a promise about what will happen.
"""

from __future__ import annotations

from dataclasses import replace

from src.application.scratchpad.lift import (
    LiftPlan,
    LiftReceipt,
    LiftTarget,
    plan_lift,
)
from src.application.scratchpad.service import ScratchpadService
from src.domain.scratchpad import Link, LinkVerdict, ModelRef, Note, scratchpad_from_parts

PERMITTED = LinkVerdict(kind="permitted", message="archimate-realization is permitted here.")
REFUSED = LinkVerdict(kind="refused", code="E126", message="not a permitted triple.")
NARROWED = LinkVerdict(kind="narrowed", code="W128", message="a specialization restricts this.")


def _pad(**overrides: object):  # noqa: ANN202 — the aggregate's own type, as the domain suite does
    defaults: dict[str, object] = {"artifact_id": "SCR@1.a.pad", "name": "Pad"}
    return scratchpad_from_parts(**{**defaults, **overrides})  # type: ignore[arg-type]


def _typed(note_id: str, title: str, element_type: str = "capability") -> Note:
    return Note(id=note_id, title=title, destination="element", element_type=element_type)


def _always(verdict: LinkVerdict):  # noqa: ANN202
    return lambda _link: verdict


class TestTheLiftItself:
    def test_an_empty_selection_is_a_mis_click_rather_than_a_request_to_lift_nothing(self) -> None:
        plan = plan_lift(
            _pad(notes=[_typed("n1", "Grow")]),
            selection=[], targets={}, verdict_of=_always(PERMITTED),
        )

        assert plan.blocks
        assert "Nothing is selected" in plan.refusal
        assert plan.items == ()

    def test_a_selection_naming_a_note_this_scratchpad_lacks_is_refused(self) -> None:
        plan = plan_lift(
            _pad(notes=[_typed("n1", "Grow")]),
            selection=["n1", "ghost"], targets={}, verdict_of=_always(PERMITTED),
        )

        assert plan.blocks
        assert "ghost" in plan.refusal

    def test_a_target_declaring_another_meta_ontology_is_a_refusal_not_a_coercion(self) -> None:
        plan = plan_lift(
            _pad(notes=[_typed("n1", "Grow")], meta_ontology="archimate-4"),
            selection=["n1"],
            targets={"unfiled": LiftTarget(group="control-systems", meta_ontology="sysml-v2", exists=True)},
            verdict_of=_always(PERMITTED),
        )

        assert plan.blocks
        assert "sysml-v2" in plan.refusal and "archimate-4" in plan.refusal

    def test_a_target_that_does_not_exist_yet_is_planned_rather_than_refused(self) -> None:
        # "This thinking has become a project" is the normal way a project starts.
        plan = plan_lift(
            _pad(notes=[_typed("n1", "Grow")]),
            selection=["n1"],
            targets={"unfiled": LiftTarget(group="q3-expansion", exists=False)},
            verdict_of=_always(PERMITTED),
        )

        assert not plan.blocks
        assert [target.group for target in plan.targets] == ["q3-expansion"]
        assert not plan.targets[0].exists


class TestWhatBecomesOfANote:
    def test_a_typed_note_is_created_carrying_its_type_body_and_specialization(self) -> None:
        note = Note(
            id="n1", title="Grow into mid-market", body="The reason we are here",
            destination="element", element_type="goal", specialization="strategic-goal",
        )

        plan = plan_lift(
            _pad(notes=[note]), selection=["n1"], targets={},
            verdict_of=_always(PERMITTED),
        )

        created = plan.of("create")[0]
        assert created.artifact_type == "goal"
        assert created.summary == "The reason we are here"
        assert created.specializations == ("strategic-goal",)

    def test_a_bound_note_is_skipped_and_the_report_names_what_it_already_is(self) -> None:
        bound = Note(
            id="n1", title="Order management", destination="element", element_type="capability",
            model_ref=ModelRef(artifact_id="ENT@9.x.order-management", kind="bound"),
        )

        plan = plan_lift(
            _pad(notes=[bound]), selection=["n1"], targets={},
            verdict_of=_always(PERMITTED),
        )

        skipped = plan.of("skip")[0]
        assert skipped.artifact_id == "ENT@9.x.order-management"
        assert not plan.blocks and plan.is_empty

    def test_a_realized_note_is_skipped_too_because_a_lift_never_writes_back(self) -> None:
        realized = Note(
            id="n1", title="Lifted last week", destination="element", element_type="capability",
            model_ref=ModelRef(artifact_id="ENT@8.y.lifted", kind="realized"),
        )

        plan = plan_lift(
            _pad(notes=[realized]), selection=["n1"], targets={},
            verdict_of=_always(PERMITTED),
        )

        assert plan.of("skip")[0].outcome == "skip"
        assert "not the scratchpad's to rewrite" in plan.of("skip")[0].reason

    def test_an_undecided_note_is_refused_and_told_what_it_needs(self) -> None:
        plan = plan_lift(
            _pad(notes=[Note(id="n1", title="Still thinking")]),
            selection=["n1"], targets={}, verdict_of=_always(PERMITTED),
        )

        assert plan.blocks
        assert "undecided" in plan.of("refuse")[0].reason

    def test_a_note_destined_for_a_document_becomes_one(self) -> None:
        plan = plan_lift(
            _pad(notes=[Note(id="n1", title="Vision", destination="document", document_type="vision")]),
            selection=["n1"], targets={}, verdict_of=_always(PERMITTED),
        )

        created = plan.of("create")[0]
        assert created.kind == "document" and created.artifact_type == "vision"
        assert not plan.blocks

    def test_a_document_note_with_no_document_type_chosen_is_refused(self) -> None:
        plan = plan_lift(
            _pad(notes=[Note(id="n1", title="Vision", destination="document")]),
            selection=["n1"], targets={}, verdict_of=_always(PERMITTED),
        )

        assert plan.blocks
        assert "no document type" in plan.of("refuse")[0].reason


class TestWhatBecomesOfALink:
    def _two_notes_and_a_link(self, **link_fields: object):  # noqa: ANN202
        return _pad(
            notes=[_typed("n1", "Goal"), _typed("n2", "Requirement")],
            links=[Link(id="l1", source="n1", target="n2", **link_fields)],  # type: ignore[arg-type]
        )

    def test_a_typed_permitted_link_between_two_created_notes_addresses_both_by_alias(self) -> None:
        plan = plan_lift(
            self._two_notes_and_a_link(connection_type="archimate-realization"),
            selection=["n1", "n2"], targets={}, verdict_of=_always(PERMITTED),
        )

        connection = next(item for item in plan.of("create") if item.kind == "connection")
        # `$ref:` is what lets a lift create both ends and the relation in one transaction.
        assert connection.source_ref == "$ref:n1"
        assert connection.target_ref == "$ref:n2"

    def test_a_link_to_a_bound_note_addresses_the_entity_that_already_exists(self) -> None:
        pad = _pad(
            notes=[
                _typed("n1", "Goal"),
                Note(id="n2", title="Order management", destination="element",
                     element_type="capability",
                     model_ref=ModelRef(artifact_id="ENT@9.x.order-management", kind="bound")),
            ],
            links=[Link(id="l1", source="n1", target="n2", connection_type="archimate-realization")],
        )

        plan = plan_lift(
            pad, selection=["n1", "n2"], targets={}, verdict_of=_always(PERMITTED),
        )

        connection = next(item for item in plan.of("create") if item.kind == "connection")
        assert connection.target_ref == "ENT@9.x.order-management"

    def test_an_untyped_link_is_refused(self) -> None:
        plan = plan_lift(
            self._two_notes_and_a_link(),
            selection=["n1", "n2"], targets={}, verdict_of=_always(PERMITTED),
        )

        assert plan.blocks
        assert "untyped" in next(item for item in plan.of("refuse") if item.kind == "connection").reason

    def test_a_refused_triple_blocks_the_whole_lift_and_carries_its_code(self) -> None:
        plan = plan_lift(
            self._two_notes_and_a_link(connection_type="archimate-serving"),
            selection=["n1", "n2"], targets={}, verdict_of=_always(REFUSED),
        )

        refused = next(item for item in plan.of("refuse") if item.kind == "connection")
        assert refused.code == "E126"
        assert plan.blocks

    def test_a_narrowing_warns_and_passes_because_the_relation_exists(self) -> None:
        plan = plan_lift(
            self._two_notes_and_a_link(connection_type="archimate-realization"),
            selection=["n1", "n2"], targets={}, verdict_of=_always(NARROWED),
        )

        assert not plan.blocks
        assert plan.warnings and "specialization" in plan.warnings[0].warning

    def test_an_already_realized_link_is_skipped_so_a_second_lift_adds_only_what_is_new(self) -> None:
        plan = plan_lift(
            self._two_notes_and_a_link(
                connection_type="archimate-realization",
                model_ref=ModelRef(artifact_id="CON@7.z.realizes", kind="realized"),
            ),
            selection=["n1", "n2"], targets={}, verdict_of=_always(PERMITTED),
        )

        skipped = next(item for item in plan.of("skip") if item.kind == "connection")
        assert skipped.artifact_id == "CON@7.z.realizes"


class TestLinksThatReachOutside:
    def test_a_link_with_one_end_outside_the_selection_is_named_rather_than_dropped(self) -> None:
        pad = _pad(
            notes=[_typed("n1", "Inside"), _typed("n2", "Outside")],
            links=[Link(id="l1", source="n1", target="n2", connection_type="archimate-serving")],
        )

        plan = plan_lift(pad, selection=["n1"], targets={}, verdict_of=_always(PERMITTED))

        # Not a refusal: it is a decision, made by extending the selection or accepting the loss.
        assert not plan.blocks
        assert plan.outside_selection[0].link_id == "l1"
        assert plan.outside_selection[0].note_title == "Outside"
        assert not any(item.kind == "connection" for item in plan.items)

    def test_a_link_wholly_outside_the_selection_is_not_reported_at_all(self) -> None:
        pad = _pad(
            notes=[_typed("n1", "Inside"), _typed("n2", "Out"), _typed("n3", "Also out")],
            links=[Link(id="l1", source="n2", target="n3", connection_type="archimate-serving")],
        )

        plan = plan_lift(pad, selection=["n1"], targets={}, verdict_of=_always(PERMITTED))

        assert plan.outside_selection == ()


class _Repository:
    """Enough of `ScratchpadRepositoryPort` to watch what the service writes back."""

    def __init__(self, scratchpad) -> None:  # noqa: ANN001 — the aggregate's own type
        self.stored = scratchpad
        self.saved_with: str | None = None

    def load(self, _artifact_id: str):  # noqa: ANN202
        return self.stored

    def group_of(self, _artifact_id: str) -> str:
        return "strategy-and-value"

    def save(self, scratchpad, *, group: str, expected_version: str | None = None):  # noqa: ANN001, ANN202, ARG002
        self.stored = scratchpad
        self.saved_with = expected_version
        return scratchpad


class _Writer:
    """A `LiftWriterPort` that records rather than writes."""

    def __init__(self, receipt: LiftReceipt | None = None, target: LiftTarget | None = None) -> None:
        self.receipt = receipt or LiftReceipt()
        self.target = target or LiftTarget()
        self.executed: list[LiftPlan] = []

    def resolve_target(self, group: str) -> LiftTarget:
        return replace(self.target, group=group or self.target.group)

    def execute(self, plan: LiftPlan, *, meta_ontology: str, dry_run: bool) -> LiftReceipt:  # noqa: ARG002
        self.executed.append(plan)
        return self.receipt


def _service(scratchpad, writer: _Writer) -> tuple[ScratchpadService, _Repository]:  # noqa: ANN001
    repository = _Repository(scratchpad)
    # The registry is only reached to build verdicts, and every case here supplies its own links'
    # types explicitly, so `None` is honest: this suite is about what the service does with a plan.
    return ScratchpadService(repository, None, writer), repository  # type: ignore[arg-type]


class TestPerformingALift:
    def _pad_with_one_liftable_note(self):  # noqa: ANN202
        return _pad(notes=[_typed("n1", "Grow into mid-market")])

    def test_a_dry_run_plans_and_writes_nothing(self) -> None:
        writer = _Writer()
        service, repository = _service(self._pad_with_one_liftable_note(), writer)

        plan, receipt = service.lift(
            "SCR@1.a.pad", selection=["n1"], targets={}, expected_version="0.1.0",
        )

        assert plan.of("create")
        assert writer.executed == [] and not receipt.committed
        assert repository.saved_with is None

    def test_a_blocked_plan_never_reaches_the_write_path(self) -> None:
        writer = _Writer()
        service, _ = _service(_pad(notes=[Note(id="n1", title="Undecided")]), writer)

        plan, _ = service.lift(
            "SCR@1.a.pad", selection=["n1"], targets={}, expected_version="0.1.0",
            dry_run=False,
        )

        assert plan.blocks
        assert writer.executed == []

    def test_a_committed_lift_records_the_realization_on_the_note(self) -> None:
        writer = _Writer(LiftReceipt(committed=True, realized={"n1": "ENT@5.q.grow"}))
        service, repository = _service(self._pad_with_one_liftable_note(), writer)

        _plan, receipt = service.lift(
            "SCR@1.a.pad", selection=["n1"], targets={"unfiled": "q3"}, expected_version="0.1.4",
            dry_run=False,
        )

        note = repository.stored.note("n1")
        assert receipt.committed
        assert note.model_ref == ModelRef(artifact_id="ENT@5.q.grow", kind="realized")
        # Written against the version the caller read: a lift is a write like any other.
        assert repository.saved_with == "0.1.4"

    def test_nothing_left_to_create_skips_the_write_path_entirely(self) -> None:
        bound = Note(
            id="n1", title="Order management", destination="element", element_type="capability",
            model_ref=ModelRef(artifact_id="ENT@9.x.order-management", kind="bound"),
        )
        writer = _Writer()
        service, _ = _service(_pad(notes=[bound]), writer)

        plan, _ = service.lift(
            "SCR@1.a.pad", selection=["n1"], targets={}, expected_version="0.1.0",
            dry_run=False,
        )

        assert plan.is_empty and not plan.blocks
        assert writer.executed == []


class TestDocumentsAndTheReferencesTheyRecord:
    """A document is the other destination, and the only one whose links are not connections."""

    def _document_and_element(self, **link_fields: object):  # noqa: ANN202
        return _pad(
            notes=[
                Note(id="d1", title="Q3 vision", destination="document", document_type="vision"),
                _typed("n1", "Order management"),
            ],
            links=[Link(id="l1", source="n1", target="d1", **link_fields)],  # type: ignore[arg-type]
        )

    def test_a_link_touching_a_document_becomes_a_reference_not_a_connection(self) -> None:
        plan = plan_lift(
            self._document_and_element(), selection=["d1", "n1"], targets={},
            verdict_of=_always(PERMITTED),
        )

        reference = next(item for item in plan.items if item.kind == "reference")
        assert reference.outcome == "create"
        assert "one-way" in reference.reason

    def test_the_reference_runs_document_to_model_whichever_way_it_was_drawn(self) -> None:
        # The link above was drawn element → document; the reference is recorded the other way, and
        # the direction drawn is deliberately not preserved. A reference the *model* held would make
        # the model depend on a commentary about it.
        plan = plan_lift(
            self._document_and_element(), selection=["d1", "n1"], targets={},
            verdict_of=_always(PERMITTED),
        )

        reference = next(item for item in plan.items if item.kind == "reference")
        assert reference.source_ref == "$ref:d1"
        assert reference.target_ref == "$ref:n1"

    def test_it_is_folded_into_the_document_it_is_recorded_on(self) -> None:
        # A reference is not an artifact: it is written as part of the document, so it cannot
        # outlive a failed document create and needs no second transaction to stay consistent.
        plan = plan_lift(
            self._document_and_element(), selection=["d1", "n1"], targets={},
            verdict_of=_always(PERMITTED),
        )

        document = next(item for item in plan.items if item.kind == "document")
        assert document.entity_refs == ("$ref:n1",)

    def test_two_documents_produce_nothing_because_they_relate_in_prose(self) -> None:
        pad = _pad(
            notes=[
                Note(id="d1", title="Vision", destination="document", document_type="vision"),
                Note(id="d2", title="Outline", destination="document", document_type="vision"),
            ],
            links=[Link(id="l1", source="d1", target="d2")],
        )

        plan = plan_lift(pad, selection=["d1", "d2"], targets={}, verdict_of=_always(PERMITTED))

        assert next(item for item in plan.items if item.kind == "reference").outcome == "skip"
        assert not plan.blocks


class TestOneTargetPerFrame:
    """The frames are work archetypes, so a canvas routinely holds work for more than one project."""

    def _two_frames(self):  # noqa: ANN202
        from src.domain.scratchpad import Area, Layout, Point, Rect

        return _pad(
            areas=[Area(id="strategy", label="Vision & strategy"), Area(id="project", label="Project")],
            notes=[_typed("n1", "Grow"), _typed("n2", "Order service")],
            layout=Layout(
                areas={"strategy": Rect(0, 0, 400, 200), "project": Rect(0, 300, 400, 200)},
                notes={"n1": Point(40, 40), "n2": Point(40, 340)},
            ),
        )

    def test_each_frame_sends_its_notes_to_its_own_project(self) -> None:
        plan = plan_lift(
            self._two_frames(),
            selection=["n1", "n2"],
            targets={
                "strategy": LiftTarget(group="enterprise-strategy", exists=True),
                "project": LiftTarget(group="q3-expansion", exists=False),
            },
            verdict_of=_always(PERMITTED),
        )

        landing = {item.id: item.target for item in plan.of("create")}
        assert landing == {"n1": "enterprise-strategy", "n2": "q3-expansion"}
        assert [target.group for target in plan.targets] == ["enterprise-strategy", "q3-expansion"]

    def test_a_frame_with_no_target_named_lands_in_the_root_model(self) -> None:
        plan = plan_lift(
            self._two_frames(),
            selection=["n1", "n2"],
            targets={"project": LiftTarget(group="q3-expansion")},
            verdict_of=_always(PERMITTED),
        )

        assert {item.id: item.target for item in plan.of("create")} == {"n1": "", "n2": "q3-expansion"}

    def test_a_mismatch_on_any_one_target_refuses_the_lift(self) -> None:
        plan = plan_lift(
            self._two_frames(),
            selection=["n1", "n2"],
            targets={
                "strategy": LiftTarget(group="fine"),
                "project": LiftTarget(group="control-systems", meta_ontology="sysml-v2", exists=True),
            },
            verdict_of=_always(PERMITTED),
        )

        assert plan.blocks and "sysml-v2" in plan.refusal

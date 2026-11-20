"""A whole-document write is held to the transitions the aggregate's own mutations permit.

Both surfaces write a scratchpad whole, so the rules about what a note may stop being were reachable
only by calling the mutation that states them — which no write did. These compare a stored state
with a submitted one, as the write path does, and assert the same sentence comes back that the
mutation gives.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.domain.ontology_representation.classification_levels import DERIVED_DEFAULT_LEVELS
from src.domain.scratchpad import (
    ModelRef,
    Note,
    Scratchpad,
    ScratchpadError,
    refuse_forbidden_transitions,
    scratchpad_from_parts,
)


def _pad(*notes: Note, meta_ontology: str = "archimate-4") -> Scratchpad:
    return scratchpad_from_parts(
        artifact_id="SCR@1.a.pad", name="Pad", notes=notes, meta_ontology=meta_ontology
    )


def _refusal(stored: Scratchpad, submitted: Scratchpad) -> str:
    with pytest.raises(ScratchpadError) as refused:
        refuse_forbidden_transitions(stored, submitted)
    return str(refused.value)


def _mutation_refusal(act: object) -> str:
    with pytest.raises(ScratchpadError) as refused:
        act()  # type: ignore[operator]
    return str(refused.value)


_REALIZED = Note(
    id="n1", title="A", destination="element", element_type="requirement",
    model_ref=ModelRef("REQ@1.a.x", "realized"),
)
_BOUND = Note(
    id="n1", title="A", destination="element", element_type="capability",
    model_ref=ModelRef("CAP@1.a.x", "bound"),
)
_TYPED = Note(id="n1", title="A", destination="element", element_type="requirement")
_REALIZED_DOCUMENT = Note(
    id="n1", title="A", destination="document", document_type="adr",
    model_ref=ModelRef("ADR@1.a.x", "realized"),
)


class TestTheMetaOntologyFreezesOnceAnythingIsTyped:
    def test_a_submitted_document_may_not_change_it_under_a_typed_note(self) -> None:
        stored = _pad(_TYPED)

        assert _refusal(stored, replace(stored, meta_ontology="sysml-v2-min")) == _mutation_refusal(
            lambda: stored.with_meta_ontology("sysml-v2-min")
        )

    def test_a_note_narrowed_no_further_than_its_first_level_freezes_it_too(self) -> None:
        stored = _pad(Note(id="n1", title="A", destination="element", domain="motivation"))

        assert "cannot change meta-ontology" in _refusal(
            stored, replace(stored, meta_ontology="sysml-v2-min")
        )

    def test_untyping_and_changing_it_are_two_writes(self) -> None:
        """Asked of the stored notes, so the vocabulary changes only once nothing is typed in it."""
        stored = _pad(_TYPED)
        emptied = _pad(Note(id="n1", title="A"), meta_ontology="sysml-v2-min")

        assert "Untype them first" in _refusal(stored, emptied)
        refuse_forbidden_transitions(stored, _pad(Note(id="n1", title="A")))
        refuse_forbidden_transitions(_pad(Note(id="n1", title="A")), emptied)

    def test_it_may_change_while_nothing_is_typed(self) -> None:
        stored = _pad(Note(id="n1", title="A"))

        refuse_forbidden_transitions(stored, replace(stored, meta_ontology="sysml-v2-min"))


class TestANoteTiedToTheModelKeepsItsType:
    @pytest.mark.parametrize("stored_note", [_REALIZED, _BOUND])
    def test_it_may_not_be_retyped(self, stored_note: Note) -> None:
        stored = _pad(stored_note)
        submitted = _pad(replace(stored_note, element_type="goal"))

        assert _refusal(stored, submitted) == _mutation_refusal(
            lambda: stored.refined(
                "n1", level=DERIVED_DEFAULT_LEVELS[1], value="goal", levels=DERIVED_DEFAULT_LEVELS
            )
        )

    @pytest.mark.parametrize("stored_note", [_REALIZED, _BOUND])
    def test_it_may_not_take_a_specialization_it_did_not_have(self, stored_note: Note) -> None:
        stored = _pad(stored_note)

        assert "takes its type from" in _refusal(
            stored, _pad(replace(stored_note, specialization="narrower"))
        )

    def test_a_bound_note_is_unbound_rather_than_untyped(self) -> None:
        """The reference kept and the type dropped is an untyping; the mutation says what to do."""
        stored = _pad(_BOUND)
        # Not built through the validating constructor: the state is one the invariants also refuse,
        # and the transition is what this asks about.
        submitted = replace(stored, notes=(replace(_BOUND, destination="undecided", element_type=None),))

        assert _refusal(stored, submitted) == _mutation_refusal(lambda: stored.untyped("n1"))

    def test_it_may_not_be_sent_to_a_document(self) -> None:
        stored = _pad(_REALIZED)
        submitted = replace(stored, notes=(replace(
            _REALIZED, destination="document", element_type=None, document_type="adr",
        ),))

        assert _refusal(stored, submitted) == _mutation_refusal(
            lambda: stored.documented("n1", document_type="adr")
        )

    def test_a_realized_document_keeps_the_type_it_was_lifted_as(self) -> None:
        stored = _pad(_REALIZED_DOCUMENT)

        assert "forget the realization" in _refusal(
            stored, _pad(replace(_REALIZED_DOCUMENT, document_type="standard"))
        )

    def test_a_realized_note_may_not_be_pointed_at_something_else(self) -> None:
        stored = _pad(_REALIZED)
        submitted = _pad(replace(_REALIZED, model_ref=ModelRef("REQ@1.b.other", "bound")))

        assert _refusal(stored, submitted) == _mutation_refusal(
            lambda: stored.bound("n1", artifact_id="REQ@1.b.other", element_type="requirement")
        )


class TestWhatStaysFree:
    def test_a_note_tied_to_the_model_may_still_be_reworded(self) -> None:
        stored = _pad(_REALIZED)

        refuse_forbidden_transitions(stored, _pad(replace(_REALIZED, title="B", body="More")))

    def test_an_untied_note_is_retyped_and_untyped_at_will(self) -> None:
        stored = _pad(_TYPED)

        refuse_forbidden_transitions(stored, _pad(replace(_TYPED, element_type="goal")))
        refuse_forbidden_transitions(stored, _pad(Note(id="n1", title="A")))

    def test_forgetting_a_realization_frees_the_note_in_the_same_write(self) -> None:
        stored = _pad(_REALIZED)

        refuse_forbidden_transitions(
            stored, _pad(replace(_REALIZED, model_ref=None, element_type="goal"))
        )

    def test_unbinding_returns_the_note_to_undecided(self) -> None:
        refuse_forbidden_transitions(_pad(_BOUND), _pad(Note(id="n1", title="A")))

    def test_binding_brings_its_type_with_it(self) -> None:
        refuse_forbidden_transitions(_pad(_TYPED), _pad(_BOUND))

    def test_a_bound_note_may_be_bound_to_something_else(self) -> None:
        rebound = replace(_BOUND, element_type="goal", model_ref=ModelRef("GOL@1.a.y", "bound"))

        refuse_forbidden_transitions(_pad(_BOUND), _pad(rebound))

    def test_a_removed_note_and_a_new_one_are_not_transitions(self) -> None:
        refuse_forbidden_transitions(_pad(_REALIZED), _pad(Note(id="n2", title="New")))

    def test_two_notes_may_exchange_a_binding_in_one_write(self) -> None:
        """Guards look at one note each, so no intermediate state is validated — replaying the
        mutations would refuse this for the moment both notes hold the same entity."""
        other = Note(id="n2", title="B")
        stored = _pad(_BOUND, other)
        submitted = _pad(
            Note(id="n1", title="A"),
            replace(other, destination="element", element_type="capability",
                    model_ref=_BOUND.model_ref),
        )

        refuse_forbidden_transitions(stored, submitted)

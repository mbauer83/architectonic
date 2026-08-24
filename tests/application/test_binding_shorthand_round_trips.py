"""Normalising the shorthand away and putting it back are held against each other.

`strip_diagram_shorthand` is deliberately lossy: `backing_entity_id` and friends come off the item
because the top-level `bindings:` block is canonical. Every consumer that still reads the shorthand is
therefore reading a field the persist path guarantees is absent. The domain records three that did; two
more were found afterwards — the ArchiMate occurrence renderer, which *requires* it, and the editor's
`occurrencesOf`, which matches on it and so could not see a stored occurrence as a drawing of anything.

So the shorthand needs an inverse, and the pair needs a test rather than an inspection: state the round
trip over what the schema *permits*, not over what one diagram happens to hold today.
"""

from __future__ import annotations

import pytest

from src.application.modeling.binding_normalize import (
    normalize_bindings,
    restore_diagram_shorthand,
    strip_diagram_shorthand,
)
from src.domain.diagrams.bindings import bindings_to_raw


def _round_trip(diagram_entities: dict, raw_bindings: list | None = None) -> dict:
    """Author with shorthand, persist, then prepare for a renderer — the real sequence."""
    canonical = normalize_bindings(diagram_entities, raw_bindings)
    persisted = strip_diagram_shorthand(dict(diagram_entities)) or {}
    restored = restore_diagram_shorthand(persisted, bindings_to_raw(list(canonical)))
    return restored or {}


class TestTheShorthandSurvivesThePersistPath:
    def test_an_occurrence_keeps_the_entity_it_draws_again(self) -> None:
        authored = {"occurrence": [{"id": "occ-repo-2", "backing_entity_id": "BOB@1.aa.repo"}]}

        assert _round_trip(authored) == authored

    def test_several_occurrences_of_several_entities_all_survive(self) -> None:
        authored = {
            "occurrence": [
                {"id": "occ-repo-2", "backing_entity_id": "BOB@1.aa.repo"},
                {"id": "occ-repo-3", "backing_entity_id": "BOB@1.aa.repo"},
                {"id": "occ-arch-2", "backing_entity_id": "ACT@1.bb.architect"},
            ]
        }

        assert _round_trip(authored) == authored

    @pytest.mark.parametrize("element_type", ["occurrence", "swimlane", "action", "classifier"])
    def test_it_holds_for_any_element_type_the_schema_permits(self, element_type: str) -> None:
        """Over what the notation permits rather than over the one type this was found through: the
        shorthand is declared on items generally, and a type-specific inverse would be the same defect
        one type along."""
        authored = {element_type: [{"id": "el-1", "backing_entity_id": "APP@1.cc.svc"}]}

        assert _round_trip(authored) == authored

    def test_an_element_declaring_nothing_gains_nothing(self) -> None:
        """Absence must survive too, or an unbound element acquires a correspondence it never made."""
        authored = {"swimlane": [{"id": "lane_you", "label": "You"}]}

        assert _round_trip(authored) == authored


class TestWhatTheInverseWillNotDo:
    def test_it_does_not_overwrite_a_caller_that_still_holds_its_shorthand(self) -> None:
        """An in-flight write carries the caller's own statement; the canonical block is the store's
        answer to the same question, and the caller's is the newer one."""
        in_flight = {"occurrence": [{"id": "occ-1", "backing_entity_id": "APP@1.new.value"}]}
        stale_canonical = [
            {"id": "bind-occ-1", "subject": {"kind": "entity", "id": "occ-1"},
             "correspondence_kind": "represents", "target": {"entity_id": "APP@1.old.value"}},
        ]

        restored = restore_diagram_shorthand(in_flight, stale_canonical)

        assert restored == in_flight

    def test_it_invents_nothing_when_no_binding_names_the_element(self) -> None:
        entities = {"occurrence": [{"id": "occ-unbound"}]}

        assert restore_diagram_shorthand(entities, []) == entities

    def test_a_diagram_level_binding_is_not_pushed_onto_an_element(self) -> None:
        """`scoped-by` on the diagram says what the view covers. Attaching it to an element that
        happened to share the id would make that element a second drawing of the diagram's subject."""
        entities = {"occurrence": [{"id": "occ-1"}]}
        scope_only = [
            {"id": "bind-scope", "subject": {"kind": "diagram"},
             "correspondence_kind": "scoped-by", "target": {"entity_id": "APP@1.backend"}},
        ]

        assert restore_diagram_shorthand(entities, scope_only) == entities

    def test_nothing_to_restore_leaves_the_mapping_identical(self) -> None:
        assert restore_diagram_shorthand(None, []) is None
        assert restore_diagram_shorthand({}, []) == {}


class TestTheRendererCanThenSeeIt:
    def test_the_occurrence_renderer_resolves_a_restored_item(self) -> None:
        """The consumer this was found through, end to end: it *requires* the shorthand, so a
        restored item is the difference between four duplicate drawings and none."""
        from pathlib import Path

        from src.domain.ontology_representation.artifact_types import EntityRecord
        from src.infrastructure.rendering.archimate_occurrences import occurrence_entities

        backing = EntityRecord(
            artifact_id="BOB@1.aa.repo", artifact_type="business-object", name="Repo",
            version="0.1.0", status="draft", domain="business", subdomain="", path=Path("e.md"),
            keywords=(), extra={}, content_text="", display_blocks={}, display_label="Repo",
            display_alias="BOB_aa",
        )
        persisted = {"occurrence": [{"id": "occ-repo-2"}]}
        canonical = [
            {"id": "bind-occ-repo-2", "subject": {"kind": "entity", "id": "occ-repo-2"},
             "correspondence_kind": "represents", "target": {"entity_id": "BOB@1.aa.repo"}},
        ]
        by_id = {backing.artifact_id: backing}

        assert occurrence_entities(persisted, by_id) == []
        restored = restore_diagram_shorthand(persisted, canonical)
        drawn = occurrence_entities(restored, by_id)

        assert [entity.display_alias for entity in drawn] == ["BOB_aa__2"]

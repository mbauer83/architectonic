"""Every correspondence an element declares, with the kind that gives it meaning.

A binding was stored, verified, reachable through the MCP tools — and shown nowhere, so an element
bound to a model entity looked exactly like an unbound one on every diagram type. `element_entity_ids`
existed and was the near-miss: it answers "which entity does this element represent", keeping the first
target and dropping the kind, which is right for a caller that navigates somewhere and wrong for a
reader being told what the element means.
"""

from __future__ import annotations

from src.domain.diagrams.element_correspondence import (
    ElementCorrespondence,
    element_correspondences,
    element_entity_ids,
)


def _binding(subject_id: str, kind: str, entity_id: str, *, subject_kind: str = "entity") -> dict:
    return {
        "id": f"bind-{subject_id}-{kind}",
        "subject": {"kind": subject_kind, "id": subject_id},
        "correspondence_kind": kind,
        "target": {"entity_id": entity_id},
    }


class TestWhatAnElementDeclares:
    def test_one_correspondence_carries_its_kind(self) -> None:
        found = element_correspondences([_binding("lane_sys", "represents", "APP@1.svc")])

        assert found == {"lane_sys": (ElementCorrespondence("represents", "APP@1.svc"),)}

    def test_every_correspondence_is_kept_in_declaration_order(self) -> None:
        """An element may represent one entity and trace to another; a reader shown one of the two
        learns something false about the other."""
        found = element_correspondences([
            _binding("a1", "represents", "FNC@1.doit"),
            _binding("a1", "traces-to", "REQ@1.why"),
        ])

        assert found["a1"] == (
            ElementCorrespondence("represents", "FNC@1.doit"),
            ElementCorrespondence("traces-to", "REQ@1.why"),
        )

    def test_a_diagram_level_binding_is_not_an_element_correspondence(self) -> None:
        """`scoped-by` on the diagram says what the *view* covers, not what an element means — it is
        how every C4 diagram in this repository binds, and answering it here would attach the
        diagram's subject to whichever element happened to share its id."""
        found = element_correspondences([
            {
                "id": "bind-scope",
                "subject": {"kind": "diagram"},
                "correspondence_kind": "scoped-by",
                "target": {"entity_id": "APP@1.backend"},
            }
        ])

        assert found == {}

    def test_a_connection_subject_is_not_an_element_either(self) -> None:
        found = element_correspondences([_binding("c1", "represents", "APP@1.x", subject_kind="connection")])

        assert found == {}


class TestWhatItRefusesToInvent:
    def test_a_target_naming_no_entity_is_skipped(self) -> None:
        found = element_correspondences([
            {"id": "b", "subject": {"kind": "entity", "id": "a1"},
             "correspondence_kind": "represents", "target": {"connection_id": "X---Y@@t"}},
        ])

        assert found == {}

    def test_a_malformed_binding_is_skipped_rather_than_raising(self) -> None:
        assert element_correspondences(["not a mapping", {}, {"subject": None}]) == {}

    def test_no_bindings_block_gives_nothing(self) -> None:
        assert element_correspondences(None) == {}
        assert element_correspondences({}) == {}


class TestTheNarrowReadingAgrees:
    """`element_entity_ids` is derived from the same walk rather than repeating it — two readings of
    one block is how they come to disagree about what a binding is."""

    def test_it_keeps_the_first_declared_target(self) -> None:
        bindings = [
            _binding("a1", "represents", "FNC@1.first"),
            _binding("a1", "traces-to", "REQ@1.second"),
        ]

        assert element_entity_ids(bindings) == {"a1": "FNC@1.first"}

    def test_both_readings_cover_the_same_elements(self) -> None:
        bindings = [
            _binding("a1", "represents", "FNC@1.doit"),
            _binding("lane", "represents", "APP@1.svc"),
            {"id": "s", "subject": {"kind": "diagram"}, "correspondence_kind": "scoped-by",
             "target": {"entity_id": "APP@1.backend"}},
        ]

        assert set(element_entity_ids(bindings)) == set(element_correspondences(bindings))

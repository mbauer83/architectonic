"""Every relationship type declares how it is drawn, and the declaration is structural.

The graph explorer drew every ArchiMate relationship as one solid line with a filled head:
a composition looked exactly like a realization looked exactly like an association. The cause
was that nothing outside the PlantUML renderer knew what a relationship should look like —
`puml_arrow` is a PlantUML spelling, and PlantUML expresses containment by nesting, so
composition and aggregation are both `-->` there and their defining diamonds do not exist.

So the ontology now declares notation directly. These tests hold two properties:

* every relationship the ontology defines says how it is drawn, and says it in terms a
  renderer can honour without knowing what the relationship *is*; and
* the distinctions the ArchiMate specification makes actually survive into that declaration —
  a notation that rendered everything identically would satisfy the first property alone.
"""

from __future__ import annotations

import pytest

from src.domain.ontology_representation.relation_notation import (
    DEFAULT_NOTATION,
    RelationNotation,
    is_known_end_marker,
    is_known_line_style,
    parse_relation_notation,
)
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry


@pytest.fixture(scope="module")
def catalogs():
    return build_runtime_catalogs(get_module_registry())


def _notation(catalogs, conn_type: str) -> dict[str, str]:
    return dict(catalogs.connections.relation_notation(conn_type))


class TestParsing:
    def test_a_missing_declaration_falls_back_to_a_plain_directed_line(self) -> None:
        """An ontology that has not declared its notation renders plainly, not not-at-all."""
        assert parse_relation_notation(None) == DEFAULT_NOTATION

    def test_a_misspelled_value_falls_back_rather_than_crashing_the_load(self) -> None:
        parsed = parse_relation_notation({"line": "squiggly", "target": "unicorn"})

        assert parsed.line == DEFAULT_NOTATION.line
        assert parsed.target == DEFAULT_NOTATION.target

    def test_a_declared_notation_is_read_verbatim(self) -> None:
        parsed = parse_relation_notation(
            {"line": "dotted", "source": "filled-diamond", "target": "hollow-triangle"}
        )

        assert parsed == RelationNotation(
            line="dotted", source="filled-diamond", target="hollow-triangle"
        )


class TestTheOntologyDeclaresNotationForEverything:
    def test_every_connection_type_has_a_notation(self, catalogs) -> None:
        """Asserted over whatever the ontology defines, not a fixed list — a relationship added
        tomorrow is covered without editing this test."""
        notations = catalogs.connections.all_relation_notations()
        defined = catalogs.connections._catalog.all_connection_types()

        assert set(notations) == {str(name) for name in defined}
        assert notations, "the ontology defines no connection types at all"

    def test_every_notation_uses_only_known_shapes(self, catalogs) -> None:
        for conn_type, notation in catalogs.connections.all_relation_notations().items():
            assert is_known_line_style(notation["line"]), f"{conn_type}: {notation['line']}"
            for end in ("source", "target"):
                assert is_known_end_marker(notation[end]), f"{conn_type}.{end}: {notation[end]}"

    def test_an_unknown_relationship_still_gets_a_notation(self, catalogs) -> None:
        """A renderer meeting a type this build does not know must still draw the edge."""
        assert _notation(catalogs, "not-a-real-relationship") == DEFAULT_NOTATION.as_mapping()


class TestArchimateDistinctionsSurvive:
    """The point of the exercise: relationships that the specification draws differently must
    not come back identical. Each of these was indistinguishable before."""

    def test_composition_and_aggregation_differ_by_their_diamond(self, catalogs) -> None:
        # Both are `-->` in PlantUML, which is exactly why `puml_arrow` cannot be the authority.
        composition = _notation(catalogs, "archimate-composition")
        aggregation = _notation(catalogs, "archimate-aggregation")

        assert composition["source"] == "filled-diamond"
        assert aggregation["source"] == "hollow-diamond"
        assert composition != aggregation

    def test_realization_is_dashed_with_a_hollow_triangle(self, catalogs) -> None:
        """Dashed rather than dotted, which this declared while drawing dashed for its whole life.

        `..|>` renders `stroke-dasharray:7,7` — dashed — so the declaration and the picture had
        never agreed; nothing caught it because `..` *looks* dotted in source. The Open Group's
        normative text is behind authentication, so the correction rests on three secondary
        sources that agree realization is a dashed line with a hollow triangle, and on the
        product's own long-standing rendering. Access, whose line every source calls dotted, is
        the one that moved the other way.
        """
        assert _notation(catalogs, "archimate-realization") == {
            "line": "dashed", "source": "none", "target": "hollow-triangle",
        }

    def test_specialization_is_solid_with_a_hollow_triangle(self, catalogs) -> None:
        # Same head as realization, different line: the pair is only distinguishable if both
        # attributes are honoured.
        assert _notation(catalogs, "archimate-specialization") == {
            "line": "solid", "source": "none", "target": "hollow-triangle",
        }

    def test_association_is_an_undecorated_line(self, catalogs) -> None:
        association = _notation(catalogs, "archimate-association")

        assert association["source"] == "none"
        assert association["target"] == "none"

    def test_triggering_and_serving_differ_by_their_head(self, catalogs) -> None:
        assert _notation(catalogs, "archimate-triggering")["target"] == "filled-arrow"
        assert _notation(catalogs, "archimate-serving")["target"] == "open-arrow"

    def test_flow_and_influence_are_not_solid(self, catalogs) -> None:
        assert _notation(catalogs, "archimate-flow")["line"] == "dashed"
        assert _notation(catalogs, "archimate-influence")["line"] == "dashed"
        assert _notation(catalogs, "archimate-access")["line"] == "dotted"

    def test_the_declared_notations_are_not_all_the_same(self, catalogs) -> None:
        """The blanket assertion behind all of the above: a table that declared one shape for
        everything would pass every structural check and still be the reported defect."""
        distinct = {tuple(sorted(n.items())) for n in catalogs.connections.all_relation_notations().values()}

        assert len(distinct) > 4, f"only {len(distinct)} distinct notations across the ontology"

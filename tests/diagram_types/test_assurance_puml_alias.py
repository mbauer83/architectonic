"""One alias, because the rendered SVG is a contract with the client.

PlantUML emits a node's alias as `data-qualified-name`, and the assurance viewer maps that back to a
node id to make shapes clickable. So the alias is shared between renderer and browser, not private to
a diagram type — and it was written twice, once per type, and drifted: control-structure prefixed
`N_`, bowtie did not, while the client reconstructed the prefixed form for both.

The consequence was silent and total. A click handler is only attached to a group whose alias was
recognised, so every shape in a rendered bowtie was inert, with nothing logged and nothing failing.
"""

from __future__ import annotations

from src.diagram_types._assurance_puml_alias import ALIAS_PREFIX, safe_alias
from src.diagram_types.bowtie import notation as bowtie
from src.diagram_types.control_structure import notation as control_structure

NODE_ID = "HAZ@1781181601.2lta.003f49"


class TestEveryDiagramTypeAgrees:
    def test_bowtie_and_control_structure_render_the_same_alias(self) -> None:
        assert bowtie.safe_alias(NODE_ID) == control_structure.safe_alias(NODE_ID)

    def test_both_use_the_shared_definition(self) -> None:
        assert bowtie.safe_alias is safe_alias
        assert control_structure.safe_alias is safe_alias


class TestTheClientCanReconstructIt:
    def test_the_alias_carries_the_prefix_the_viewer_expects(self) -> None:
        """`assuranceNodeAlias` in the frontend builds `N_` + id with separators replaced. An alias
        without the prefix is never matched, and the shape is silently inert."""
        assert safe_alias(NODE_ID) == f"{ALIAS_PREFIX}HAZ_1781181601_2lta_003f49"

    def test_separators_become_single_underscores(self) -> None:
        """The frontend replaces each of @ . - with one underscore, so collapsing runs here would
        produce an alias it cannot rebuild."""
        assert safe_alias("ACN@1781181670.yg1v.bd474b") == f"{ALIAS_PREFIX}ACN_1781181670_yg1v_bd474b"

    def test_an_alias_never_starts_with_a_digit(self) -> None:
        """Which is what the prefix guarantees, rather than relying on every id prefix being alpha."""
        assert safe_alias("1234").startswith(ALIAS_PREFIX)

    def test_an_id_of_only_separators_still_yields_an_alias(self) -> None:
        assert safe_alias("@.-") == f"{ALIAS_PREFIX}node"


class TestTheRenderedPumlUsesIt:
    def test_a_bowtie_body_declares_its_nodes_under_the_shared_alias(self) -> None:
        body = bowtie.render(
            nodes=[{"node_id": NODE_ID, "node_type": "hazard", "name": "Readable outside the gate"}],
            edges=[],
            title="",
        )

        assert safe_alias(NODE_ID) in body

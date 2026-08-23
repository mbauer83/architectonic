"""A deployment host is drawn as a node whether or not anything is drawn inside it.

The C4 macro table had no row for `node`, so a host fell through to the fallback whose own comment
says *unknown item type → generic container shape*. That was invisible for as long as every host
happened to hold something, because a host with children takes the other path entirely and opens a
`Deployment_Node` boundary. A host with none renders as `Container(...)` — an **application
container** glyph, labelled with its technology, which reads as a deployed application rather than
the machine or volume it is.

It is reachable two ways, and one of them is on the shipped model: a volume whose only container is
also hosted elsewhere loses it to the other host, because containment resolves as a tree and a child
has one parent. The other way needs no defect at all — a node nobody has modelled anything onto yet.

What a node *is* does not depend on what happens to be drawn inside it, so the glyph must not either.
"""

from __future__ import annotations

from src.diagram_types.c4.renderer import _c4_macro_name


class TestTheMacroForAHost:
    def test_a_node_is_a_deployment_node(self) -> None:
        assert _c4_macro_name("node", "generic", False) == "Deployment_Node"

    def test_a_node_holding_a_store_is_still_a_node(self) -> None:
        """The `db` variant is inferred from technology, and a volume's technology can say storage.
        A node is not a database, whatever it holds."""
        assert _c4_macro_name("node", "db", False) == "Deployment_Node"

    def test_a_node_is_not_reached_by_the_unknown_type_fallback(self) -> None:
        """Guards the guard: if `node` ever stops being handled, this catches it as itself rather
        than as an equality with whatever the fallback happens to return."""
        assert _c4_macro_name("node", "generic", False) != _c4_macro_name(
            "no-such-item-type", "generic", False
        )


class TestWhatDidNotChange:
    def test_a_container_is_still_a_container(self) -> None:
        assert _c4_macro_name("container", "generic", False) == "Container"

    def test_a_container_holding_a_store_is_still_a_database(self) -> None:
        assert _c4_macro_name("container", "db", False) == "ContainerDb"

    def test_the_unknown_fallback_is_unchanged(self) -> None:
        assert _c4_macro_name("no-such-item-type", "generic", False) == "Container"

    def test_an_external_node_does_not_carry_a_suffix_that_does_not_exist(self) -> None:
        """`Deployment_Node_Ext` is not defined by the C4 deployment stdlib. Verified against the
        pinned PlantUML 1.2026.3: a body calling it reports *Some diagram description contains
        errors* and emits no diagram, while a childless `Deployment_Node` renders as a «node» box.

        So the `_Ext` suffix every other type takes would turn an external host into a broken
        render. No host is external today — the projection builds them all with role `internal` —
        which is what makes this a latent trap worth an assertion rather than a live bug.
        """
        assert _c4_macro_name("node", "generic", True) == "Deployment_Node"

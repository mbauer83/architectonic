"""Composition of layered guidance context along a concept's ancestry (broadest first),
including the type→specialization bridge and the skip-empty-layers behavior."""

from __future__ import annotations

from src.application.guidance_composition import (
    ComposedContext,
    GuidanceContextView,
    compose_context,
    compose_type_context,
)
from src.domain.guidance.guidance import GuidanceContextKey, GuidanceOverlay
from src.domain.guidance.guidance_hierarchy import GuidanceHierarchy, GuidanceLevel, GuidanceNode
from src.domain.guidance.guidance_hierarchy_source import specialization_node_id


def _hierarchy() -> GuidanceHierarchy:
    return GuidanceHierarchy(
        levels=(
            GuidanceLevel("domain", "Domain", 0),
            GuidanceLevel("entity_type", "Entity type", 1),
            GuidanceLevel("specialization", "Specialization", 2),
        ),
        nodes=(
            GuidanceNode("domain", "motivation"),
            GuidanceNode("entity_type", "requirement", parent_node_id="motivation"),
            GuidanceNode(
                "specialization",
                specialization_node_id("requirement", "constraint"),
                parent_node_id="requirement",
            ),
        ),
    )


def _overlay(context: dict[tuple[str, ...], str] | None = None) -> GuidanceOverlay:
    """An overlay whose context is keyed the way a guidance document nests it: by node path."""
    entries = {GuidanceContextKey("archimate-4", path): text for path, text in (context or {}).items()}
    return GuidanceOverlay(context_entries=entries)


_MOTIVATION = ("motivation",)
_CONSTRAINT = ("motivation", "requirement", specialization_node_id("requirement", "constraint"))


class TestComposeContext:
    def test_type_gets_domain_context(self) -> None:
        overlay = _overlay({_MOTIVATION: "WHY the architecture is shaped this way."})
        chain = compose_type_context(
            module_alias="archimate-4", hierarchy=_hierarchy(), overlay=overlay, type_name="requirement"
        )
        assert [(c.level_id, c.node_id, c.text) for c in chain] == [
            ("domain", "motivation", "WHY the architecture is shaped this way.")
        ]

    def test_specialization_composes_broadest_first(self) -> None:
        overlay = _overlay({_MOTIVATION: "domain context", _CONSTRAINT: "spec context"})
        chain = compose_type_context(
            module_alias="archimate-4",
            hierarchy=_hierarchy(),
            overlay=overlay,
            type_name="requirement",
            specialization="constraint",
        )
        assert [c.text for c in chain] == ["domain context", "spec context"]

    def test_context_keyed_by_a_bare_node_id_does_not_match_a_deeper_node(self) -> None:
        """A node's context is reached by its whole path, so a leaf cannot pick up text filed
        against a same-named node elsewhere in the tree."""
        overlay = _overlay({("requirement",): "not the path to the type under motivation"})
        chain = compose_type_context(
            module_alias="archimate-4", hierarchy=_hierarchy(), overlay=overlay, type_name="requirement"
        )
        assert chain == ()

    def test_layers_without_context_are_skipped(self) -> None:
        overlay = _overlay()  # no context anywhere
        chain = compose_type_context(
            module_alias="archimate-4", hierarchy=_hierarchy(), overlay=overlay, type_name="requirement"
        )
        assert chain == ()

    def test_unknown_node_yields_empty_chain(self) -> None:
        overlay = _overlay({_MOTIVATION: "x"})
        chain = compose_context(
            module_alias="archimate-4",
            hierarchy=_hierarchy(),
            overlay=overlay,
            leaf_level_id="entity_type",
            leaf_node_id="ghost",
        )
        assert chain == ()

    def test_other_module_alias_does_not_match(self) -> None:
        overlay = _overlay({_MOTIVATION: "x"})
        chain = compose_type_context(
            module_alias="sysml-v2", hierarchy=_hierarchy(), overlay=overlay, type_name="requirement"
        )
        assert chain == ()


class TestGuidanceContextViewWorkspace:
    """The workspace level is prepended to every ``context_for`` result — broadest of all — even
    for a type whose alias is unknown."""

    def _view(self, workspace: tuple[ComposedContext, ...]) -> GuidanceContextView:
        sources = {"archimate-4": (_hierarchy(), _overlay({_MOTIVATION: "domain context"}))}
        return GuidanceContextView(sources=sources, type_alias={"requirement": "archimate-4"}, workspace=workspace)

    def test_workspace_is_prepended_before_the_module_chain(self) -> None:
        ws = (ComposedContext("workspace", "workspace", "encode relations structurally"),)
        chain = self._view(ws).context_for("requirement")
        assert [(c.level_id, c.node_id, c.text) for c in chain] == [
            ("workspace", "workspace", "encode relations structurally"),
            ("domain", "motivation", "domain context"),
        ]

    def test_workspace_included_even_for_unknown_alias(self) -> None:
        ws = (ComposedContext("workspace", "workspace", "state principles generally"),)
        chain = self._view(ws).context_for("no-such-type")
        assert [(c.level_id, c.text) for c in chain] == [("workspace", "state principles generally")]

    def test_empty_view_is_a_noop(self) -> None:
        assert GuidanceContextView().context_for("requirement") == ()

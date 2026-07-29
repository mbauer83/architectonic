"""get_type_guidance attaches the additive v2 `context` array (composed ancestry context)
to an entity type when the RuntimeCatalogs carries a populated guidance-context view, and
omits it otherwise — leaving create_when/never_create_when untouched either way."""

from __future__ import annotations

import dataclasses
from functools import lru_cache

from src.application.guidance_composition import GuidanceContextView
from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.guidance.guidance import GuidanceContextKey, GuidanceOverlay
from src.domain.guidance.guidance_hierarchy import GuidanceHierarchy, GuidanceLevel, GuidanceNode
from src.infrastructure.write.artifact_write.type_guidance import get_type_guidance


@lru_cache(maxsize=1)
def _base() -> RuntimeCatalogs:
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs

    return build_runtime_catalogs(build_module_registry())


def _view_with_motivation_context() -> GuidanceContextView:
    hierarchy = GuidanceHierarchy(
        levels=(GuidanceLevel("domain", "Domain", 0), GuidanceLevel("entity_type", "Entity type", 1)),
        nodes=(
            GuidanceNode("domain", "motivation"),
            GuidanceNode("entity_type", "requirement", parent_node_id="motivation"),
        ),
    )
    overlay = GuidanceOverlay(
        context_entries={GuidanceContextKey("archimate-4", ("motivation",)): "Motivation context text."}
    )
    return GuidanceContextView(
        sources={"archimate-4": (hierarchy, overlay)}, type_alias={"requirement": "archimate-4"}
    )


def _requirement_entry(result: dict) -> dict:
    return next(e for e in result["entity_types"] if e["name"] == "requirement")


def test_context_attached_when_view_has_context() -> None:
    cats = dataclasses.replace(_base(), guidance_context=_view_with_motivation_context())
    entry = _requirement_entry(get_type_guidance(filter=["requirement"], catalogs=cats))
    assert entry["context"] == [{"level": "domain", "node": "motivation", "text": "Motivation context text."}]
    # existing fields untouched (the additive-only guarantee)
    assert "create_when" in entry and "never_create_when" in entry


def test_context_absent_with_default_empty_view() -> None:
    cats = dataclasses.replace(_base(), guidance_context=GuidanceContextView())
    entry = _requirement_entry(get_type_guidance(filter=["requirement"], catalogs=cats))
    assert "context" not in entry


def test_unrelated_type_gets_no_context() -> None:
    # 'goal' is not in the view's type_alias, so no context is attached to it.
    cats = dataclasses.replace(_base(), guidance_context=_view_with_motivation_context())
    result = get_type_guidance(filter=["goal"], catalogs=cats)
    goal = next(e for e in result["entity_types"] if e["name"] == "goal")
    assert "context" not in goal

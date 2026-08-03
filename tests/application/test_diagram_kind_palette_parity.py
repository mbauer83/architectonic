"""The diagram-kind palette has two transports and one answer.

`GET /api/diagram-types/{t}/entity-types` and its connection twin are the only address on the surface
that answers "which *types* may this diagram hold": `/api/diagram-types` gives labels, `ui-config` gives
rendering hints, and `artifact_authoring_guidance(diagram_type=…)` gave accepted **domains** and prose.
So an agent asking the tool whose job this is was told the domains and left to derive the type list —
the same derivation, done less well, and with no way to reproduce the viewpoint-narrowed form at all.

Both now read `application.modeling.diagram_kind_palette`. This file is what keeps that true. The four
`search_nodes` implementations are the reason it exists: three identical copies and a fourth that was
quietly better, with nothing anywhere asserting they agreed. A palette exposed on two transports is the
same arrangement, and the only difference is that this one has a test before the divergence rather than
after.

**No new tool and no new parameter**, which was the constraint. `artifact_authoring_guidance` already
took `diagram_type`; what changed is what it *answers*, which costs no tool surface. A `diagram_palette`
tool would have been a second address for a question this tool is already asked.
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture(scope="module")
def catalogs() -> Any:
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs

    return build_runtime_catalogs(build_module_registry())


#: One diagram kind per language shape, so a divergence cannot hide in the kind nobody checked.
#: Read from the catalogue rather than listed, because a hard-coded list is a list that goes stale —
#: and `test_every_declared_diagram_kind_has_a_palette` is what makes the coverage claim true.
def _kinds(catalogs: Any) -> list[str]:
    return sorted(str(name) for name in catalogs.diagram_types.all_diagram_types())


def test_every_declared_diagram_kind_has_a_palette(catalogs: Any) -> None:
    """The precondition for the parity assertions: they must actually be comparing something.

    A palette builder that raised, or answered `[]` for everything, would make every equality below
    trivially true — which is the shape of a green test that checks nothing.
    """
    from src.application.modeling.diagram_kind_palette import diagram_kind_entity_types

    kinds = _kinds(catalogs)
    assert len(kinds) >= 3, kinds

    non_empty = [kind for kind in kinds if diagram_kind_entity_types(kind, catalogs)]
    assert non_empty, "no diagram kind accepts any entity type; the palette is answering nothing"


def test_the_guidance_tool_answers_the_palette_the_rest_route_serves(catalogs: Any) -> None:
    """The parity assertion, over every declared kind.

    Compared as whole lists rather than as sets: the *order* is part of the answer — entity types come in
    the ontology's domain order, which is what makes a palette readable — so a change that reordered one
    transport and not the other would be a real divergence a set comparison would miss.
    """
    from src.infrastructure.rest.routers.diagrams._context import (
        diagram_kind_connection_type_items,
        diagram_kind_entity_type_items,
    )
    from src.infrastructure.write.artifact_write.type_guidance import get_type_guidance

    for kind in _kinds(catalogs):
        guidance = get_type_guidance(diagram_type=kind, catalogs=catalogs)
        block = guidance.get("diagram_type_guidance")
        assert isinstance(block, dict), (kind, guidance)

        assert block["accepted_entity_types"] == diagram_kind_entity_type_items(kind, catalogs), kind
        assert block["accepted_connection_types"] == diagram_kind_connection_type_items(
            kind, catalogs
        ), kind


def test_the_palette_is_answered_even_without_a_filter(catalogs: Any) -> None:
    """The exact gap this closed, named so it cannot reopen.

    `get_type_guidance` skips its entity/connection sections entirely when `diagram_type` is given and
    `filter` is not — `if filter is not None or diagram_type is None`. So the agent flow that asks only
    "what about this diagram type" got domains and prose and no types at all, while the flow that also
    passed a filter got types that were the *filter's* subset rather than the diagram's palette.
    """
    kind = _kinds(catalogs)[0]

    from src.infrastructure.write.artifact_write.type_guidance import get_type_guidance

    block = get_type_guidance(diagram_type=kind, catalogs=catalogs)["diagram_type_guidance"]

    assert isinstance(block, dict)
    assert "accepted_entity_types" in block, block.keys()
    assert "accepted_connection_types" in block, block.keys()
    # And the coarser answer is still there: the types are additive, not a replacement. An agent reading
    # `accepted_domains` today must keep working.
    assert "when_to_use" in block


def test_a_narrowing_scope_can_only_remove_types(catalogs: Any) -> None:
    """The property a viewpoint narrowing must have, asserted without needing a viewpoint.

    REST narrows by `?viewpoint=`, which resolves to a `ConceptScope`; the guidance tool takes no
    viewpoint and so passes none. Either way the scope must be a *filter* — a narrowing that admitted a
    type the diagram kind does not accept would be inventing palette entries, and the effective
    authoring scope is an intersection by definition.
    """
    from src.application.modeling.diagram_kind_palette import diagram_kind_entity_types
    from src.domain.concept_scope import ConceptScope

    kind = next(k for k in _kinds(catalogs) if diagram_kind_entity_types(k, catalogs))
    unnarrowed = diagram_kind_entity_types(kind, catalogs)

    class _AdmitsNothing(ConceptScope):  # type: ignore[misc]
        def admits_entity_type(self, *_args: object, **_kwargs: object) -> bool:
            return False

    narrowed = diagram_kind_entity_types(kind, catalogs, scope=_AdmitsNothing())

    assert narrowed == [], narrowed
    assert len(unnarrowed) > len(narrowed)


def test_neither_transport_derives_the_palette_for_itself() -> None:
    """The structural half: one composition, two thin callers.

    The REST helpers are adapters now — slug to scope, then delegate — and the guidance serialiser calls
    the same module. Asserted by source, because what must not come back is a *second* comprehension
    over `effective_entity_types()`, and that is a shape rather than a behaviour.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    for relative in (
        "src/infrastructure/rest/routers/diagrams/_context.py",
        "src/infrastructure/write/artifact_write/type_guidance.py",
    ):
        source = (root / relative).read_text(encoding="utf-8")
        assert "effective_entity_types()" not in source, (
            f"{relative} is building a palette of its own again instead of asking "
            "application.modeling.diagram_kind_palette"
        )
        assert "diagram_kind_palette" in source, relative

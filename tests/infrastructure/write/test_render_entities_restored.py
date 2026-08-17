"""The render path restores what the persist path keeps elsewhere.

Two facts about a diagram are canonical outside ``diagram_entities`` and have to be put back before
the renderer, which reads only that mapping: the scope, from the ``scoped-by`` binding, and the
membership a derivation has ratified, from ``view_derivations[].selection``.

The round trip is stated over what the syntax *permits*, not over what any writer emits today: a
selection may hold several derivations, may hold none, and may be overridden by an explicit key.
"""

from __future__ import annotations

from src.domain.diagrams.bindings import (
    EXCLUDED_IDS_KEY,
    INCLUDED_IDS_KEY,
    SCOPE_KEY,
    parse_bindings,
)
from src.infrastructure.write.artifact_write.diagram_render_input import render_entities_restored

_SCOPE_BINDING = [
    {
        "id": "bind-scope",
        "subject": {"kind": "diagram"},
        "correspondence_kind": "scoped-by",
        "target": {"entity_id": "APP@1.aaaaaa.backend"},
    }
]


def _derivation(*included: str, derivation_id: str = "d1") -> dict[str, object]:
    return {
        "id": derivation_id,
        "strategy": "viewpoint_execution",
        "strategy_version": 1,
        "source_model_snapshot": {"repo_scope": "both"},
        "selection": {"included_entity_ids": list(included)},
    }


def test_ratified_membership_reaches_the_renderer() -> None:
    """A derivation's agreed content is what the diagram draws — it must not stop at the frontmatter."""
    restored = render_entities_restored(
        {}, parse_bindings(_SCOPE_BINDING), [_derivation("APP@1.bbbbbb.queue", "APP@1.cccccc.registry")]
    )

    assert restored[INCLUDED_IDS_KEY] == ["APP@1.bbbbbb.queue", "APP@1.cccccc.registry"]
    assert restored[SCOPE_KEY] == "APP@1.aaaaaa.backend"


def test_several_derivations_contribute_one_membership() -> None:
    """`view_derivations` is a list and entries are addressed by id, so a diagram may carry several.

    A C4 diagram is expected to carry two — its own scope projection and a viewpoint execution — so
    the union, deduplicated and order-preserving, is the contract rather than "the first one".
    """
    restored = render_entities_restored(
        {},
        parse_bindings(_SCOPE_BINDING),
        [
            _derivation("APP@1.bbbbbb.queue", derivation_id="scope-projection"),
            _derivation("APP@1.cccccc.registry", "APP@1.bbbbbb.queue", derivation_id="viewpoint"),
        ],
    )

    assert restored[INCLUDED_IDS_KEY] == ["APP@1.bbbbbb.queue", "APP@1.cccccc.registry"]


def test_an_explicit_inclusion_outranks_a_stored_derivation() -> None:
    """What the caller states now beats what was stored earlier — the same rule the scope follows.

    This guard is also what makes the restoration additive: every diagram authored with a literal
    list keeps rendering exactly as it did before derivations were consulted at all.
    """
    restored = render_entities_restored(
        {INCLUDED_IDS_KEY: ["APP@1.dddddd.authored"]},
        parse_bindings(_SCOPE_BINDING),
        [_derivation("APP@1.bbbbbb.queue")],
    )

    assert restored[INCLUDED_IDS_KEY] == ["APP@1.dddddd.authored"]


def test_an_exclusion_list_also_suppresses_restoration() -> None:
    """The two keys are mutually exclusive, so a stated exclusion must not gain a rival inclusion."""
    restored = render_entities_restored(
        {EXCLUDED_IDS_KEY: ["APP@1.eeeeee.dropped"]},
        parse_bindings(_SCOPE_BINDING),
        [_derivation("APP@1.bbbbbb.queue")],
    )

    assert INCLUDED_IDS_KEY not in restored


def test_no_derivations_and_empty_selections_change_nothing() -> None:
    """Restoration is silent where there is nothing to restore, so an unrelated diagram is untouched."""
    bindings = parse_bindings(_SCOPE_BINDING)

    assert INCLUDED_IDS_KEY not in render_entities_restored({}, bindings, None)
    assert INCLUDED_IDS_KEY not in render_entities_restored({}, bindings, [])
    assert INCLUDED_IDS_KEY not in render_entities_restored({}, bindings, [_derivation()])

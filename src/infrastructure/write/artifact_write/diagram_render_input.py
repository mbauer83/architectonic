"""What the renderer is given: `diagram-entities` with everything the persist path keeps elsewhere.

Beside the module that *runs* the renderer rather than inside it, because these are two concerns and
the file said so by outgrowing its limit. Preparing an input is not producing an output, and only one
of the two knows what a diagram's frontmatter keeps where.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.application.modeling.binding_normalize import restore_diagram_shorthand
from src.domain.diagrams.bindings import (
    EXCLUDED_IDS_KEY,
    INCLUDED_IDS_KEY,
    SCOPE_IDS_KEY,
    SCOPE_KEY,
    Binding,
    bindings_to_raw,
    scope_shorthand,
    scope_target,
)
from src.domain.viewpoints.view_derivations import parse_view_derivations


def render_entities_restored(
    diagram_entities: dict[str, object],
    bindings: Iterable[Binding],
    view_derivations: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """The renderer's input, with everything the persist path keeps elsewhere put back.

    Three facts about a diagram are canonical outside `diagram_entities` and have to be restored
    before the renderer, which reads only that mapping: the scope, which lives in the top-level
    `bindings:` block; the membership a derivation has ratified, which lives in
    `view_derivations[].selection`; and which model entity an ArchiMate occurrence is a second
    drawing of, which the persist path strips from the item and keeps as a `represents` binding.

    The third was missing, and `occurrence_entities` *requires* the stripped field — so a diagram whose
    occurrences had been normalised resolved none of them, and a regenerating edit drew none of the
    duplicates. It is the same shape as the scope: the renderer reads one mapping, and the canonical
    home is elsewhere.

    Restoring both lives here, beside the render call, rather than being spelled at each of the two
    write paths that make one. That is not tidiness — the create path and the edit path each had
    their own copy of the scope restoration, and each read only the singular target, so a diagram
    scoped by a *set* rendered as if it had no scope at all. A second restoration with a second
    pair of copies is the same defect waiting.
    """
    restored = _with_scope(dict(diagram_entities), bindings)
    restored = restore_diagram_shorthand(restored, bindings_to_raw(list(bindings))) or restored
    return _with_ratified_selection(restored, view_derivations)


def _with_scope(diagram_entities: dict[str, object], bindings: Iterable[Binding]) -> dict[str, object]:
    target = scope_target(bindings)
    if target is None or SCOPE_KEY in diagram_entities or SCOPE_IDS_KEY in diagram_entities:
        return diagram_entities
    key, value = scope_shorthand(target)
    return {**diagram_entities, key: value}


def _with_ratified_selection(
    diagram_entities: dict[str, object], view_derivations: list[dict[str, object]] | None
) -> dict[str, object]:
    """Membership a derivation has ratified, expressed as the inclusion shorthand the renderer reads.

    `DerivationSelection.included_entity_ids` is not a list of overrides — it is what successive
    refresh-and-apply cycles have *agreed* the view contains, which is exactly what an author means
    by `_included_entity_ids`. One fact, so one key; the derivation is where it is decided and this
    is where it is spoken.

    An explicit key in `diagram_entities` wins and nothing is restored, on the same principle as the
    scope above: what the caller states now outranks what was stored earlier. That guard is also
    what makes this additive — every diagram authored with a literal list keeps rendering exactly as
    it did.
    """
    if not view_derivations:
        return diagram_entities
    if INCLUDED_IDS_KEY in diagram_entities or EXCLUDED_IDS_KEY in diagram_entities:
        return diagram_entities
    raw: list[object] = list(view_derivations)
    ratified: list[str] = []
    for derivation in parse_view_derivations(raw):
        selection = derivation.selection
        if selection is None:
            continue
        ratified.extend(eid for eid in selection.included_entity_ids if eid not in ratified)
    if not ratified:
        return diagram_entities
    return {**diagram_entities, INCLUDED_IDS_KEY: ratified}

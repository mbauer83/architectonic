"""The viewpoint projection: the unifying contract between repository execution, the
verifier's artifact-local checks, and the GUI's ghost/hide overlay.

Deliberately parallel to ``view_projection.py``'s opacity contract — same philosophy
(opaque display tokens, generic code never interprets them), different concern (derivation
preview vs. viewpoint evaluation). Pure shapes only; the application-layer projection
service that produces instances of these types is a later work unit.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

ProjectionTarget = Literal["repository", "diagram", "matrix"]
OcclusionState = Literal["visible", "ghosted"]
ExclusionReason = Literal[
    "out_of_scope",  # fails effective ConceptScope (diagram-type scope ∩ viewpoint scope)
    "criteria_mismatch",  # fails the definition's entity/connection criteria
    "endpoint_excluded",  # connection whose source/target is itself excluded
]
Membership = Literal["primary", "expanded"]


@dataclass(frozen=True)
class ProjectedOccurrence:
    """One entity's or connection's state within a projection.

    ``style`` is documented (not structurally enforced here — the producing service owns
    the invariant) to be empty whenever ``reasons`` is non-empty: an excluded occurrence is
    never styled, in every enforcement mode, because style tokens express the viewpoint's
    semantics, which an excluded item by definition does not satisfy.
    """

    item_id: str
    item_kind: Literal["entity", "connection"]
    state: OcclusionState
    membership: Membership = "primary"  # connections are always "primary"
    reasons: tuple[ExclusionReason, ...] = ()  # empty iff the item fully matches
    style: Mapping[str, object] = field(default_factory=dict)  # capability -> opaque token or scale position
    connection_type: str | None = None
    source_id: str | None = None
    target_id: str | None = None
    certainty: Literal["certain", "potential"] | None = None
    hops: int | None = None
    via_connection_ids: tuple[str, ...] = ()
    derived_match_hops: int | None = None
    """Entities only: set when the entity's criteria match REQUIRED derived-relationship
    evidence — the minimum witness-chain length it rested on. ``None`` for matches
    establishable from modeled facts alone (and for connections/expanded members)."""
    column_values: Mapping[str, object] | None = None
    """Entities only, and only when the definition authors table columns: one entry per
    authored column source, resolved server-side at execution time. A source that does
    not resolve for this entity is explicitly ``None`` — present-but-missing, never a
    silently absent key — so renderers can distinguish "no value" from "not fetched"."""


StyleRuleOutcomeKind = Literal["applied", "expected-empty", "shadowed", "unresolvable", "disabled"]


@dataclass(frozen=True)
class StyleRuleOutcome:
    """One authored style rule's observable outcome for this execution.

    Every rule reports exactly one outcome: ``applied`` (styled ``applied_count`` items),
    ``shadowed`` (matched items, but a higher-precedence rule claimed every one),
    ``expected-empty`` (valid rule, zero matches — a legitimate state, e.g. a gap rule
    over a healthy model), ``unresolvable`` (its attribute/reference cannot resolve), or
    ``disabled`` (quarantined — deliberately inert, e.g. a fork's inherited rule whose
    attribute no longer resolves). Only ``unresolvable`` and ``shadowed`` warrant
    warnings; ``expected-empty`` must stay quiet or healthy conformance views cry wolf,
    and ``disabled`` is a deliberate authoring state, not a defect.
    """

    rule_index: int
    capability: str
    kind: StyleRuleOutcomeKind
    matched_count: int = 0
    applied_count: int = 0
    detail: str | None = None  # e.g. the unresolvable attribute path


@dataclass(frozen=True)
class ViewpointProjection:
    target: ProjectionTarget
    items: tuple[ProjectedOccurrence, ...]
    stale_pin: bool = False  # artifact-local only: pinned_version < current definition version
    warnings: tuple[str, ...] = ()  # schema drift, capability drift, unresolved references
    scale_legends: tuple["ScaleLegendData", ...] = ()
    rule_outcomes: tuple[StyleRuleOutcome, ...] = ()


@dataclass(frozen=True)
class ScaleLegendData:
    """A scale's resolved bounds and endpoint tokens for a presentation adapter."""

    capability: str
    attribute: str
    minimum: float
    maximum: float
    tokens: tuple[str, str]


def drift_warnings(drift: frozenset[str]) -> tuple[str, ...]:
    """One human-readable warning per schema-drifted attribute path (degraded loudly,
    never silently"), sorted for deterministic output."""
    return tuple(f"schema drift: attribute '{attribute}' is no longer resolvable" for attribute in sorted(drift))


def rule_outcome_warnings(outcomes: tuple[StyleRuleOutcome, ...]) -> tuple[str, ...]:
    """Warnings for the two defect-class outcomes only: an unresolvable reference and a
    fully shadowed rule. ``expected-empty`` never warns — zero matches is a legitimate
    state for a healthy gap rule, and warning on it would train users to ignore warnings."""
    warnings: list[str] = []
    for outcome in outcomes:
        position = f"style rule {outcome.rule_index + 1} ({outcome.capability})"
        if outcome.kind == "unresolvable":
            warnings.append(f"{position}: reference '{outcome.detail}' cannot resolve — the rule styles nothing")
        elif outcome.kind == "shadowed":
            warnings.append(
                f"{position}: matched {outcome.matched_count} item(s), but a higher-precedence rule "
                "claimed every one — the rule styles nothing"
            )
    return tuple(warnings)


def derivation_truncation_warnings(truncated: bool) -> tuple[str, ...]:
    """A derived-relationship search stopped at its time budget before finishing — the
    result is genuine and correct, just not necessarily complete."""
    if not truncated:
        return ()
    return ("derived-relationship search stopped early after its time budget; results may be incomplete",)

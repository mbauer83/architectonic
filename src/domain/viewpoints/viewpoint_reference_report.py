"""Static reference-integrity report for a viewpoint definition.

Generalizes the style-rule "no silent no-op" contract (``StyleRuleOutcomeKind``) to EVERY
authored reference a definition carries that can break when the model changes underneath it
— retired entity/connection types, deleted specialization slugs, unresolvable attribute
paths, and entity-id anchors that no longer resolve. It is a PURE function of (definition,
current registries + read model): nothing is persisted, so a reference that comes back
self-heals with no stored buffer to invalidate.

Division of labour with the execution-time mechanisms it complements:

* Attribute-PATH breakage already surfaces at execution as schema drift
  (``drift_warnings``) and, for style rules, as an ``unresolvable`` ``StyleRuleOutcome`` —
  both keyed on the same ``resolve_attribute_path(...) is None`` condition this report uses.
  This report also ENUMERATES attribute paths so a non-executing surface (catalogue list,
  open/edit) has one authority, but ``reference_report_warnings`` omits them so execution
  never double-reports; breakage in that class instead suppresses absence claims through the
  full report.
* Reserved ``type``/``specialization`` VALUES, style ``applies_to`` slugs, target-type
  declarations, and entity-id references fail SILENTLY today (a retired type simply stops
  matching, indistinguishable from a legitimately empty result). This report is their only
  source, and ``reference_report_warnings`` surfaces them loudly.
* ``group`` and other OPEN vocabularies are advisory by design (a nonexistent value yields a
  typed empty result, not an error) and are never reported.

Renames are a non-event: entity-id references compare on the rename-stable short id
(``stable_id``), so only a genuine deletion (or a cross-tier reference whose type/slug the
destination registry does not know) registers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.domain.artifact_id import is_entity_id, stable_id
from src.domain.viewpoints.viewpoint_condition_validation import (
    CriteriaContext,
    RegistrySnapshot,
    resolve_attribute_path,
)
from src.domain.viewpoints.viewpoint_criteria import (
    AttributeCondition,
    ConnectionCriteriaGroup,
    EntityCriteriaGroup,
    IncidentConnectionCondition,
)
from src.domain.viewpoints.viewpoint_evaluation_context import CriteriaReadAccess
from src.domain.viewpoints.viewpoint_scope_query import definition_with_scope_query
from src.domain.viewpoints.viewpoints import ExecutableViewpointQuery, PresentationSpec, StyleRule, ViewpointDefinition

ReferenceKind = Literal["entity-type", "connection-type", "specialization", "attribute-path", "entity-id"]
ReferenceSeverity = Literal["ontology", "entity-id"]

_ONTOLOGY_KINDS: frozenset[str] = frozenset({"entity-type", "connection-type", "specialization", "attribute-path"})
_RESERVED_VALUE_COMPARATORS: frozenset[str] = frozenset({"eq", "neq", "in", "not_in"})
_ATTRIBUTE_PATH: ReferenceKind = "attribute-path"


@dataclass(frozen=True)
class BrokenReference:
    """One authored reference that no longer resolves against the current model."""

    kind: ReferenceKind
    reference: str
    locus: str  # human-readable location, e.g. "entity criteria" or "style rule 2 (node_color)"

    @property
    def severity(self) -> ReferenceSeverity:
        return "ontology" if self.kind in _ONTOLOGY_KINDS else "entity-id"


class _Collector:
    """Accumulates broken references, deduplicated by (kind, reference, locus) in first-seen
    order so a value referenced twice at the same locus reports once."""

    def __init__(self) -> None:
        self._seen: set[tuple[str, str, str]] = set()
        self.items: list[BrokenReference] = []

    def add(self, kind: ReferenceKind, reference: str, locus: str) -> None:
        key = (kind, reference, locus)
        if key not in self._seen:
            self._seen.add(key)
            self.items.append(BrokenReference(kind=kind, reference=reference, locus=locus))


def reference_report(
    definition: ViewpointDefinition, *, registries: RegistrySnapshot, read_access: CriteriaReadAccess
) -> tuple[BrokenReference, ...]:
    """Every broken reference in a definition's ACTIVE selection layer plus its presentation.

    Operates on the executable form (scope-mode type restrictions are translated into
    criteria), so scope and query definitions are walked uniformly.
    """
    executable, _ = definition_with_scope_query(definition)
    query = executable.query
    assert query is not None
    collector = _Collector()

    _walk_entity_group(query.entity_criteria, "entity", "entity criteria", registries, collector)
    _walk_connection_group(query.connections.criteria, "connection selection", registries, collector)
    for index, inclusion in enumerate(query.include_connected):
        label = f"included neighbours {index + 1}"
        if inclusion.connection_criteria is not None:
            _walk_connection_group(inclusion.connection_criteria, label, registries, collector)
        if inclusion.neighbor_criteria is not None:
            _walk_entity_group(inclusion.neighbor_criteria, "entity", label, registries, collector)
    for derived in query.derived:
        label = f"derived attribute '{derived.name}'"
        if derived.connection_criteria is not None:
            _walk_connection_group(derived.connection_criteria, label, registries, collector)
        if derived.endpoint_criteria is not None:
            _walk_entity_group(derived.endpoint_criteria, "entity", label, registries, collector)

    _walk_entity_id_parameters(query, read_access, collector)
    if executable.presentation is not None:
        _walk_presentation(executable.presentation, registries, collector)
    return tuple(collector.items)


def _walk_entity_group(
    group: EntityCriteriaGroup, context: CriteriaContext, locus: str, registries: RegistrySnapshot, out: _Collector
) -> None:
    for child in group.children:
        if isinstance(child, EntityCriteriaGroup):
            _walk_entity_group(child, context, locus, registries, out)
        elif isinstance(child, IncidentConnectionCondition):
            if child.connection_criteria is not None:
                _walk_connection_group(child.connection_criteria, locus, registries, out)
            if child.endpoint_criteria is not None:
                _walk_entity_group(child.endpoint_criteria, "entity", locus, registries, out)
        else:
            _check_condition(child, context, locus, registries, out)


def _walk_connection_group(
    group: ConnectionCriteriaGroup, locus: str, registries: RegistrySnapshot, out: _Collector
) -> None:
    for child in group.children:
        if isinstance(child, ConnectionCriteriaGroup):
            _walk_connection_group(child, locus, registries, out)
        else:
            _check_condition(child, "connection", locus, registries, out)


def _check_condition(
    condition: AttributeCondition, context: CriteriaContext, locus: str, registries: RegistrySnapshot, out: _Collector
) -> None:
    declared = resolve_attribute_path(condition.attribute, context=context, registries=registries)
    if declared is None:
        out.add(_ATTRIBUTE_PATH, condition.attribute, locus)
        return
    if declared == "reserved":
        _check_reserved_value(condition, context, locus, registries, out)


def _check_reserved_value(
    condition: AttributeCondition, context: CriteriaContext, locus: str, registries: RegistrySnapshot, out: _Collector
) -> None:
    """A reserved ``type``/``specialization`` literal compared to a slug the registries no
    longer know — the silent class a retired type falls into (mirrors the save-time
    ``unknown-value`` check, but reported rather than raised)."""
    if condition.value.kind != "literal" or condition.comparator not in _RESERVED_VALUE_COMPARATORS:
        return
    head = condition.attribute.split(".", 1)[0]
    kind, known = _reserved_head_vocabulary(head, context, registries)
    if known is None:
        return
    literal = condition.value.literal
    values = literal if isinstance(literal, (list, tuple)) else [literal]
    for value in values:
        if isinstance(value, str) and value not in known:
            out.add(kind, value, locus)


def _reserved_head_vocabulary(
    head: str, context: CriteriaContext, registries: RegistrySnapshot
) -> tuple[ReferenceKind, frozenset[str] | None]:
    if head == "type":
        if context == "entity":
            return "entity-type", registries.known_entity_types
        return "connection-type", registries.known_connection_types
    if head == "specialization":
        return "specialization", registries.known_specialization_slugs
    return "entity-type", None


def _walk_presentation(presentation: PresentationSpec, registries: RegistrySnapshot, out: _Collector) -> None:
    for index, rule in enumerate(presentation.styling_rules):
        if rule.disabled:
            continue  # quarantined: never evaluated, never reported (the "make it inert" affordance)
        _check_style_rule(rule, index, registries, out)
    for column in presentation.columns or ():
        if resolve_attribute_path(column.source, context="entity", registries=registries) is None:
            out.add(_ATTRIBUTE_PATH, column.source, f"column '{column.label}'")
    for axis, criteria in (("row", presentation.row_criteria), ("column", presentation.column_criteria)):
        if criteria is not None:
            _walk_entity_group(criteria, "entity", f"matrix {axis} axis", registries, out)
    for target_type in presentation.target_types or ():
        if target_type not in registries.known_entity_types:
            out.add("entity-type", target_type, "target population")


def _check_style_rule(rule: StyleRule, index: int, registries: RegistrySnapshot, out: _Collector) -> None:
    locus = f"style rule {index + 1} ({rule.capability})"
    context: CriteriaContext = "connection" if rule.capability.startswith("edge_") else "entity"
    type_kind, type_vocabulary = _reserved_head_vocabulary("type", context, registries)
    assert type_vocabulary is not None
    for value in sorted(rule.applies_to):
        # applies_to conflates type and specialization slugs; a value is valid as either.
        if value not in type_vocabulary and value not in registries.known_specialization_slugs:
            out.add(type_kind, value, locus)
    if isinstance(rule.match_criteria, EntityCriteriaGroup):
        _walk_entity_group(rule.match_criteria, "entity", locus, registries, out)
    elif isinstance(rule.match_criteria, ConnectionCriteriaGroup):
        _walk_connection_group(rule.match_criteria, locus, registries, out)
    for criteria in (rule.source_criteria, rule.target_criteria):
        if criteria is not None:
            _walk_entity_group(criteria, "entity", locus, registries, out)
    for attribute in (rule.range_attribute, rule.scale_attribute):
        if attribute is not None and not attribute.startswith("derived."):
            if resolve_attribute_path(attribute, context=context, registries=registries) is None:
                out.add(_ATTRIBUTE_PATH, attribute, locus)


def _walk_entity_id_parameters(
    query: ExecutableViewpointQuery, read_access: CriteriaReadAccess, out: _Collector
) -> None:
    """An ``entity-id`` parameter whose stored DEFAULT no longer resolves. Renames are a
    non-event — the default is compared on its rename-stable short id."""
    for parameter in query.parameters:
        if parameter.value_type != "entity-id" or not isinstance(parameter.default, str):
            continue
        default = parameter.default
        resolved = read_access.get_entity(default) or (
            read_access.get_entity(stable_id(default)) if is_entity_id(default) else None
        )
        if resolved is None:
            out.add("entity-id", default, f"parameter '{parameter.name}' default")


def reference_report_warnings(report: tuple[BrokenReference, ...]) -> tuple[str, ...]:
    """Loud warnings for the SILENT reference classes only. Attribute-path breakage is
    excluded — at execution it is already surfaced by schema-drift / style ``unresolvable``
    warnings, and re-emitting here would double-report the same defect."""
    labels: dict[str, str] = {
        "entity-type": "entity type",
        "connection-type": "connection type",
        "specialization": "specialization",
        "entity-id": "entity",
    }
    warnings: list[str] = []
    for broken in report:
        if broken.kind == _ATTRIBUTE_PATH:
            continue
        label = labels[broken.kind]
        warnings.append(
            f"{broken.locus}: references {label} '{broken.reference}', which no longer exists — "
            "results may be incomplete"
        )
    return tuple(warnings)

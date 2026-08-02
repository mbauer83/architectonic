"""Parsing for the ``query:`` block: entity criteria, neighbor inclusions, and connections."""

from __future__ import annotations

from collections.abc import Mapping

from src.domain.viewpoints.viewpoint_bindings import DerivedAttribute, QueryBinding, QueryParameter
from src.domain.viewpoints.viewpoint_criteria import (
    VALID_INCIDENT_DIRECTIONS,
    EntityCriteriaGroup,
    IncidentDirection,
)
from src.domain.viewpoints.viewpoint_criteria_parsing import (
    parse_connection_criteria_group,
    parse_connection_selection,
    parse_entity_criteria_group,
    parse_neighbor_inclusion,
)
from src.domain.viewpoints.viewpoint_set_parameters import canonicalize_set_value
from src.domain.viewpoints.viewpoint_trace_pattern_parsing import parse_trace_patterns
from src.domain.viewpoints.viewpoint_value_types import parse_result_type
from src.domain.viewpoints.viewpoints import (
    QUERY_SCHEMA_VERSION,
    VALID_REPO_SCOPES,
    ExecutableViewpointQuery,
    RepoScope,
)

_QUERY_KEYS = frozenset(
    {
        "query_schema",
        "entity_criteria",
        "include_connected",
        "connections",
        "repo_scope",
        "bindings",
        "parameters",
        "derived",
        "trace_patterns",
    }
)


def _require_repo_scope(value: object, *, label: str) -> RepoScope:
    text = str(value)
    if text not in ("enterprise", "engagement", "both"):
        raise ValueError(f"{label}: repo_scope {text!r} is not one of {sorted(VALID_REPO_SCOPES)}")
    return text


def _require_direction(value: object) -> IncidentDirection:
    text = str(value)
    if text not in VALID_INCIDENT_DIRECTIONS:
        raise ValueError(f"direction {text!r} is not one of {sorted(VALID_INCIDENT_DIRECTIONS)}")
    return text  # type: ignore[return-value]


def query_from_mapping(raw: object, *, label: str) -> ExecutableViewpointQuery:
    """Parse the ad-hoc query mapping. ``label`` names *this* mapping, as everywhere else here.

    It used to name the mapping's *container* on one raise and this mapping on every other, so the
    two callers each read wrong on half the messages: a rejection from ``POST /api/viewpoints/execute``
    said ``query: query: unknown key(s)``, while one from a stored definition said
    ``my-viewpoint: query_schema is required`` without saying which of its mappings was meant. One
    convention — the caller supplies the path, the callee appends only what it descends into —
    and both read correctly.
    """
    if not isinstance(raw, Mapping):
        return ExecutableViewpointQuery()
    if not raw:
        return ExecutableViewpointQuery()
    _check_unknown(raw, _QUERY_KEYS, label)
    if "query_schema" not in raw:
        raise ValueError(f"{label}: query_schema is required")
    schema_version = int(raw["query_schema"])
    if schema_version != QUERY_SCHEMA_VERSION:
        raise ValueError(f"{label}: unsupported query_schema {schema_version!r}, expected {QUERY_SCHEMA_VERSION}")
    entity_criteria_raw = raw.get("entity_criteria")
    entity_criteria = (
        parse_entity_criteria_group(entity_criteria_raw) if entity_criteria_raw is not None else EntityCriteriaGroup()
    )
    include_connected_raw = raw.get("include_connected", ())
    if not isinstance(include_connected_raw, (list, tuple)):
        raise ValueError(f"{label}: include_connected must be a list")
    include_connected = tuple(parse_neighbor_inclusion(item) for item in include_connected_raw)
    return ExecutableViewpointQuery(
        query_schema=schema_version,
        entity_criteria=entity_criteria,
        include_connected=include_connected,
        connections=parse_connection_selection(raw.get("connections")),
        repo_scope=_require_repo_scope(raw.get("repo_scope", "both"), label=label),
        bindings=tuple(_binding_from_mapping(item) for item in _list(raw.get("bindings", ()), "bindings")),
        parameters=tuple(_parameter_from_mapping(item) for item in _list(raw.get("parameters", ()), "parameters")),
        derived=tuple(_derived_from_mapping(item) for item in _list(raw.get("derived", ()), "derived")),
        trace_patterns=parse_trace_patterns(raw.get("trace_patterns"), label=f"{label}: trace_patterns"),
    )


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{label} must be a list")
    return list(value)


def _binding_from_mapping(raw: object) -> QueryBinding:
    if not isinstance(raw, Mapping):
        raise ValueError("binding must be a mapping")
    allowed = frozenset(
        {"name", "result_type", "select", "criteria", "project", "aggregate", "tuple", "include_in_result"}
    )
    _check_unknown(raw, allowed, "binding")
    select = raw.get("select")
    if select not in {None, "entities", "connections"}:
        raise ValueError("binding select must be entities or connections")
    criteria = raw.get("criteria")
    parsed_criteria = None
    if criteria is not None:
        if select == "entities":
            parsed_criteria = parse_entity_criteria_group(criteria)
        elif select == "connections":
            parsed_criteria = parse_connection_criteria_group(criteria)
        else:
            raise ValueError("binding criteria requires an entities or connections selection")
    tuple_of = raw.get("tuple", ())
    if not isinstance(tuple_of, (list, tuple)) or not all(isinstance(item, str) for item in tuple_of):
        raise ValueError("binding tuple must be a list of names")
    aggregate = raw.get("aggregate")
    if aggregate not in {None, "count", "sum", "avg", "min", "max"}:
        raise ValueError("binding aggregate is unknown")
    return QueryBinding(
        name=str(raw["name"]),
        result_type=parse_result_type(str(raw["result_type"])),
        select=select,
        criteria=parsed_criteria,
        project=str(raw["project"]) if raw.get("project") is not None else None,
        aggregate=aggregate,  # type: ignore[arg-type]
        tuple_of=tuple(tuple_of),
        include_in_result=bool(raw.get("include_in_result", False)),
    )


def _parameter_from_mapping(raw: object) -> QueryParameter:
    if not isinstance(raw, Mapping):
        raise ValueError("parameter must be a mapping")
    allowed_keys = frozenset(
        {"name", "type", "required", "default", "description", "cardinality", "allowed_values", "min_items"}
    )
    _check_unknown(raw, allowed_keys, "parameter")
    value_type = str(raw["type"])
    if value_type not in {"string", "integer", "number", "date", "boolean", "slug", "entity-id"}:
        raise ValueError("parameter type is unknown")
    cardinality = str(raw.get("cardinality", "one"))
    if cardinality not in {"one", "many"}:
        raise ValueError("parameter cardinality must be one or many")
    if cardinality == "many":
        return _set_parameter(raw, value_type)
    for set_only in ("allowed_values", "min_items"):
        if set_only in raw:
            raise ValueError(f"{set_only} requires cardinality: many")
    return QueryParameter(
        name=str(raw["name"]),
        value_type=value_type,  # type: ignore[arg-type]
        required=bool(raw.get("required", True)),
        default=raw.get("default"),
        description=str(raw.get("description", "")),
    )


def _set_parameter(raw: Mapping[str, object], value_type: str) -> QueryParameter:
    """A ``cardinality: many`` parameter. ``allowed_values`` is OPTIONAL: present = a closed
    vocabulary (members enforced, declaration order canonical); absent = an open vocabulary
    (anything accepted, sorted order canonical) — which is what a group filter needs, since
    group names are live repo state, not an authorable constant."""
    allowed_raw = raw.get("allowed_values")
    allowed_values: tuple[str, ...] = ()
    if allowed_raw is not None:
        if not isinstance(allowed_raw, (list, tuple)) or not allowed_raw:
            raise ValueError("allowed_values must be a non-empty list when declared")
        if not all(isinstance(value, str) for value in allowed_raw):
            raise ValueError("allowed_values members must be strings")
        allowed_values = tuple(str(value) for value in allowed_raw)
        if len(set(allowed_values)) != len(allowed_values):
            raise ValueError("allowed_values must be unique")
    default_raw = raw.get("default")
    default: tuple[str, ...] | None = None
    if default_raw is not None:
        if not isinstance(default_raw, (list, tuple)):
            raise ValueError("a set-valued parameter's default must be a list")
        canonical, unknown = canonicalize_set_value(default_raw, allowed_values)
        if unknown:
            raise ValueError(f"default has member(s) outside allowed_values: {list(unknown)}")
        default = canonical
    min_items = raw.get("min_items", 1)
    if not isinstance(min_items, int) or isinstance(min_items, bool):
        raise ValueError("min_items must be an integer")
    return QueryParameter(
        name=str(raw["name"]),
        value_type=value_type,  # type: ignore[arg-type]
        cardinality="many",
        required=bool(raw.get("required", True)),
        default=default,
        description=str(raw.get("description", "")),
        allowed_values=allowed_values,
        min_items=min_items,
    )


def _derived_from_mapping(raw: object) -> DerivedAttribute:
    if not isinstance(raw, Mapping):
        raise ValueError("derived attribute must be a mapping")
    allowed = frozenset(
        {
            "name",
            "source",
            "metric",
            "direction",
            "traversal",
            "include_potential",
            "max_hops",
            "connection_criteria",
            "endpoint_criteria",
            "reduce",
            "of",
        }
    )
    _check_unknown(raw, allowed, "derived attribute")
    source = str(raw.get("source", "graph"))
    if source not in {"graph", "security-signal"}:
        raise ValueError("derived attribute source is unknown")
    if source == "security-signal":
        if not str(raw.get("metric") or ""):
            raise ValueError("security-signal derived attribute requires a metric name")
        graph_only = {
            "direction", "traversal", "include_potential", "max_hops",
            "connection_criteria", "endpoint_criteria", "reduce", "of",
        } & set(raw)
        if graph_only:
            raise ValueError(
                f"security-signal derived attribute must not carry graph keys {sorted(graph_only)}"
            )
        return DerivedAttribute(
            name=str(raw["name"]),
            source="security-signal",
            metric=str(raw["metric"]),
        )
    if raw.get("metric") is not None:
        raise ValueError("metric is only valid with source: security-signal")
    traversal = str(raw.get("traversal", "direct"))
    if traversal not in {"direct", "derived"}:
        raise ValueError("derived attribute traversal is unknown")
    reduce = str(raw.get("reduce", "count"))
    if reduce not in {"count", "sum", "avg", "min", "max"}:
        raise ValueError("derived attribute reduce is unknown")
    return DerivedAttribute(
        name=str(raw["name"]),
        direction=_require_direction(raw.get("direction", "either")),
        traversal=traversal,  # type: ignore[arg-type]
        include_potential=bool(raw.get("include_potential", False)),
        max_hops=int(raw["max_hops"]) if raw.get("max_hops") is not None else None,
        connection_criteria=(
            parse_connection_criteria_group(raw["connection_criteria"])
            if raw.get("connection_criteria") is not None
            else None
        ),
        endpoint_criteria=(
            parse_entity_criteria_group(raw["endpoint_criteria"]) if raw.get("endpoint_criteria") is not None else None
        ),
        reduce=reduce,  # type: ignore[arg-type]
        of=str(raw["of"]) if raw.get("of") is not None else None,
    )


def _check_unknown(raw: Mapping[str, object], allowed: frozenset[str], label: str) -> None:
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f"{label}: unknown key(s) {sorted(unknown)}")

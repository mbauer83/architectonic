"""Parsing for the ``trace_patterns:`` block into ``TracePatternSet`` domain shapes.

Structural parsing only: unknown keys, unknown tagged variants, missing required fields, and
wrong scalar shapes raise ``TracePatternError`` with a stable code. Cross-pattern concerns —
dangling/cyclic refs, name uniqueness, and the structural caps that need the whole set (and
``{ref}`` expansion) — are the validator's job, so a single pattern parses in isolation here.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.domain.viewpoints.viewpoint_trace_patterns import (
    ERR_MISSING_FIELD,
    ERR_UNKNOWN_FIELD,
    ERR_UNKNOWN_KIND,
    ERR_UNKNOWN_VARIANT,
    VALID_DIAGNOSTIC_STATUSES,
    VALID_EDGE_DIRECTIONS,
    VALID_LEAF_TRAVERSALS,
    VALID_REALIZER_REGISTRIES,
    Branches,
    BranchesRef,
    DerivedReachabilityLeaf,
    DiagnosticEdge,
    EdgeDirection,
    InlineBranches,
    LayerMembershipEndpoint,
    Leaf,
    LeafEndpoint,
    NamedBranchEdge,
    NoneLeaf,
    RegistryEndpoint,
    RollupEdge,
    StoredEdge,
    TracePattern,
    TracePatternError,
    TracePatternSet,
)

_PATTERN_KEYS = frozenset(
    {"name", "kind", "applies_to", "branches", "shortcuts", "leaf", "rollup", "diagnostic"}
)
_STORED_EDGE_KEYS = frozenset({"kind", "connection", "direction", "endpoint"})
_DIAGNOSTIC_EDGE_KEYS = frozenset({"kind", "connection", "direction", "endpoint", "status"})
_ROLLUP_EDGE_KEYS = frozenset({"kind", "connection", "direction", "endpoint"})
_DERIVED_LEAF_KEYS = frozenset({"kind", "connection", "traversal", "max_hops", "endpoint"})
# Leaf endpoints target a realizer set (registry) or a layer (domain[+class]); the ``type``
# key belongs to EDGE endpoints only (enforced inline in ``_endpoint_type``).
_LEAF_ENDPOINT_KEYS = frozenset({"registry", "domain", "class"})


def parse_trace_patterns(raw: object, *, label: str) -> TracePatternSet:
    """Parse the ``trace_patterns`` list. Absent/empty yields an empty set (viewpoints without
    trace patterns are the norm)."""
    if raw is None:
        return TracePatternSet()
    if not isinstance(raw, (list, tuple)):
        raise TracePatternError(ERR_UNKNOWN_VARIANT, f"{label}: trace_patterns must be a list")
    return TracePatternSet(tuple(_pattern(item, label=label) for item in raw))


def _mapping(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TracePatternError(ERR_UNKNOWN_VARIANT, f"{label}: expected a mapping")
    return value


def _check_keys(raw: Mapping[str, object], allowed: frozenset[str], *, label: str) -> None:
    unknown = set(raw) - allowed
    if unknown:
        raise TracePatternError(ERR_UNKNOWN_FIELD, f"{label}: unknown key(s) {sorted(unknown)}")


def _require(raw: Mapping[str, object], key: str, *, label: str) -> object:
    if key not in raw:
        raise TracePatternError(ERR_MISSING_FIELD, f"{label}: {key} is required")
    return raw[key]


def _int(value: object, *, label: str) -> int:
    # ``bool`` is an ``int`` subclass; reject it so ``max_hops: true`` is a variant error.
    if isinstance(value, bool) or not isinstance(value, int):
        raise TracePatternError(ERR_UNKNOWN_VARIANT, f"{label}: expected an integer")
    return value


def _pattern(item: object, *, label: str) -> TracePattern:
    raw = _mapping(item, label=label)
    name = str(_require(raw, "name", label=label))
    scoped = f"{label}: pattern {name!r}"
    _check_keys(raw, _PATTERN_KEYS, label=scoped)
    kind = str(raw.get("kind", "branch-complete-realization"))
    if kind != "branch-complete-realization":
        raise TracePatternError(ERR_UNKNOWN_KIND, f"{scoped}: unknown kind {kind!r}")
    applies_to = _require(raw, "applies_to", label=scoped)
    if not isinstance(applies_to, (list, tuple)) or not all(isinstance(t, str) for t in applies_to):
        raise TracePatternError(ERR_UNKNOWN_VARIANT, f"{scoped}: applies_to must be a list of type names")
    shortcuts = tuple(_diagnostic_edge(s, label=scoped) for s in _optional_list(raw.get("shortcuts"), label=scoped))
    return TracePattern(
        name=name,
        applies_to=tuple(str(t) for t in applies_to),
        branches=_branches(_require(raw, "branches", label=scoped), label=scoped),
        shortcuts=shortcuts,
        leaf=_leaf(raw.get("leaf"), label=scoped),
        rollup=_rollup(raw.get("rollup"), label=scoped),
        diagnostic=bool(raw.get("diagnostic", False)),
    )


def _optional_list(value: object, *, label: str) -> list[object]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise TracePatternError(ERR_UNKNOWN_VARIANT, f"{label}: expected a list")
    return list(value)


def _branches(value: object, *, label: str) -> Branches:
    raw = _mapping(value, label=f"{label} branches")
    if "ref" in raw:
        if set(raw) != {"ref"}:
            raise TracePatternError(ERR_UNKNOWN_FIELD, f"{label} branches: a ref carries only 'ref'")
        return BranchesRef(str(raw["ref"]))
    edges = tuple(
        NamedBranchEdge(str(edge_label), _stored_edge(edge, label=f"{label} branch {edge_label!r}"))
        for edge_label, edge in raw.items()
    )
    return InlineBranches(edges)


def _direction(value: object, *, label: str) -> EdgeDirection:
    text = str(value)
    if text not in VALID_EDGE_DIRECTIONS:
        raise TracePatternError(
            ERR_UNKNOWN_VARIANT, f"{label}: direction {text!r} not in {sorted(VALID_EDGE_DIRECTIONS)}"
        )
    return text  # type: ignore[return-value]


def _endpoint_type(raw: Mapping[str, object], *, label: str) -> str:
    endpoint = _mapping(_require(raw, "endpoint", label=label), label=f"{label} endpoint")
    if set(endpoint) != {"type"}:
        raise TracePatternError(ERR_UNKNOWN_FIELD, f"{label} endpoint: an edge endpoint carries only 'type'")
    return str(endpoint["type"])


def _stored_edge(value: object, *, label: str) -> StoredEdge:
    raw = _mapping(value, label=label)
    kind = str(raw.get("kind", "stored-edge"))
    if kind != "stored-edge":
        raise TracePatternError(ERR_UNKNOWN_VARIANT, f"{label}: branch edges must be stored-edge, got {kind!r}")
    _check_keys(raw, _STORED_EDGE_KEYS, label=label)
    return StoredEdge(
        connection=str(_require(raw, "connection", label=label)),
        direction=_direction(_require(raw, "direction", label=label), label=label),
        endpoint_type=_endpoint_type(raw, label=label),
    )


def _rollup(value: object, *, label: str) -> RollupEdge | None:
    """The optional whole-part edge a row's verdict composes over. Absent means no composition."""
    if value is None:
        return None
    raw = _mapping(value, label=f"{label} rollup")
    kind = str(raw.get("kind", "rollup-edge"))
    if kind != "rollup-edge":
        raise TracePatternError(ERR_UNKNOWN_VARIANT, f"{label} rollup: must be rollup-edge, got {kind!r}")
    _check_keys(raw, _ROLLUP_EDGE_KEYS, label=f"{label} rollup")
    return RollupEdge(
        connection=str(_require(raw, "connection", label=f"{label} rollup")),
        direction=_direction(_require(raw, "direction", label=f"{label} rollup"), label=f"{label} rollup"),
        endpoint_type=_endpoint_type(raw, label=f"{label} rollup"),
    )


def _diagnostic_edge(value: object, *, label: str) -> DiagnosticEdge:
    raw = _mapping(value, label=label)
    kind = str(raw.get("kind", "diagnostic-edge"))
    if kind != "diagnostic-edge":
        raise TracePatternError(ERR_UNKNOWN_VARIANT, f"{label}: shortcuts must be diagnostic-edge, got {kind!r}")
    _check_keys(raw, _DIAGNOSTIC_EDGE_KEYS, label=label)
    status = str(_require(raw, "status", label=label))
    if status not in VALID_DIAGNOSTIC_STATUSES:
        raise TracePatternError(
            ERR_UNKNOWN_VARIANT, f"{label}: status {status!r} not in {sorted(VALID_DIAGNOSTIC_STATUSES)}"
        )
    return DiagnosticEdge(
        connection=str(_require(raw, "connection", label=label)),
        direction=_direction(_require(raw, "direction", label=label), label=label),
        endpoint_type=_endpoint_type(raw, label=label),
        status=status,  # type: ignore[arg-type]
    )


def _leaf(value: object, *, label: str) -> Leaf:
    if value is None:
        return NoneLeaf()
    raw = _mapping(value, label=f"{label} leaf")
    kind = str(_require(raw, "kind", label=f"{label} leaf"))
    if kind == "none":
        if set(raw) != {"kind"}:
            raise TracePatternError(ERR_UNKNOWN_FIELD, f"{label} leaf: a none leaf carries only 'kind'")
        return NoneLeaf()
    if kind != "derived-reachability":
        raise TracePatternError(ERR_UNKNOWN_VARIANT, f"{label} leaf: unknown kind {kind!r}")
    _check_keys(raw, _DERIVED_LEAF_KEYS, label=f"{label} leaf")
    traversal = str(raw.get("traversal", "direct_and_derived"))
    if traversal not in VALID_LEAF_TRAVERSALS:
        raise TracePatternError(ERR_UNKNOWN_VARIANT, f"{label} leaf: traversal {traversal!r} unsupported")
    return DerivedReachabilityLeaf(
        connection=str(_require(raw, "connection", label=f"{label} leaf")),
        endpoint=_leaf_endpoint(_require(raw, "endpoint", label=f"{label} leaf"), label=f"{label} leaf"),
        max_hops=_int(raw.get("max_hops", 4), label=f"{label} leaf max_hops"),
        traversal=traversal,  # type: ignore[arg-type]
    )


def _leaf_endpoint(value: object, *, label: str) -> LeafEndpoint:
    raw = _mapping(value, label=f"{label} endpoint")
    _check_keys(raw, _LEAF_ENDPOINT_KEYS, label=f"{label} endpoint")
    if "registry" in raw:
        registry = str(raw["registry"])
        if registry not in VALID_REALIZER_REGISTRIES:
            raise TracePatternError(ERR_UNKNOWN_VARIANT, f"{label} endpoint: unknown registry {registry!r}")
        return RegistryEndpoint(registry)  # type: ignore[arg-type]
    if "domain" in raw:
        entity_class = raw.get("class")
        return LayerMembershipEndpoint(str(raw["domain"]), str(entity_class) if entity_class is not None else None)
    raise TracePatternError(ERR_UNKNOWN_VARIANT, f"{label} endpoint: expected a 'registry' or 'domain' target")

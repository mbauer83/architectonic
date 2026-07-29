"""Cross-pattern validation + ``{ref}`` expansion for the trace-pattern grammar.

Per-item structural shape is already guaranteed by the parser; this module judges the SET:
name uniqueness, the structural caps, and reference integrity (dangling, cyclic,
depth, count). ``expand_branch_edges`` resolves a pattern's branches to its effective ordered
stored edges — immutable value-expansion used by both the edge-count cap here and the
evaluator; it raises the typed code, which validation converts into issues so a definition
never half-loads.
"""

from __future__ import annotations

from src.domain.viewpoints.viewpoint_condition_validation import issue
from src.domain.viewpoints.viewpoint_trace_patterns import (
    ERR_CYCLIC_REF,
    ERR_DANGLING_REF,
    ERR_REF_DEPTH,
    MAX_EDGE_DECLARATIONS,
    MAX_LEAF_HOPS,
    MAX_REF_EXPANSION_DEPTH,
    MAX_TRACE_PATTERNS,
    BranchesRef,
    DerivedReachabilityLeaf,
    EdgeDeclaration,
    InlineBranches,
    NamedBranchEdge,
    TracePattern,
    TracePatternError,
    TracePatternSet,
)
from src.domain.viewpoints.viewpoint_validation_issue import ViewpointValidationIssue


def expand_branch_edges(pattern: TracePattern, patterns: TracePatternSet) -> tuple[NamedBranchEdge, ...]:
    """Resolve ``pattern``'s branches to its effective ordered stored edges, following ``{ref}``
    chains. Raises ``TracePatternError`` on a dangling reference, a cycle, or depth beyond the
    cap — only branch edges expand, never the referent's shortcuts/leaf/status."""
    seen: tuple[str, ...] = (pattern.name,)
    branches = pattern.branches
    depth = 0
    while isinstance(branches, BranchesRef):
        here = f"pattern {pattern.name!r}"
        if depth >= MAX_REF_EXPANSION_DEPTH:
            raise TracePatternError(ERR_REF_DEPTH, f"{here}: ref chain exceeds depth {MAX_REF_EXPANSION_DEPTH}")
        if branches.ref in seen:
            raise TracePatternError(ERR_CYCLIC_REF, f"{here}: cyclic branches ref via {branches.ref!r}")
        target = patterns.by_name(branches.ref)
        if target is None:
            raise TracePatternError(ERR_DANGLING_REF, f"{here}: branches ref {branches.ref!r} not found")
        seen += (branches.ref,)
        branches = target.branches
        depth += 1
    return branches.edges if isinstance(branches, InlineBranches) else ()


def validate_trace_patterns(
    patterns: TracePatternSet, *, path: str, check_ergonomics: bool
) -> list[ViewpointValidationIssue]:
    issues: list[ViewpointValidationIssue] = []
    if check_ergonomics and len(patterns.patterns) > MAX_TRACE_PATTERNS:
        issues.append(
            issue("error", "trace-pattern-count-exceeded", path,
                  f"a viewpoint declares at most {MAX_TRACE_PATTERNS} trace patterns")
        )
    seen: set[str] = set()
    for index, pattern in enumerate(patterns.patterns):
        item_path = f"{path}/{index}"
        if pattern.name in seen:
            issues.append(issue("error", "trace-pattern-duplicate-name", f"{item_path}/name",
                                "trace pattern name must be unique"))
        seen.add(pattern.name)
        issues.extend(_validate_pattern(pattern, patterns, path=item_path, check_ergonomics=check_ergonomics))
    return issues


def _validate_pattern(
    pattern: TracePattern, patterns: TracePatternSet, *, path: str, check_ergonomics: bool
) -> list[ViewpointValidationIssue]:
    issues: list[ViewpointValidationIssue] = []
    if not pattern.applies_to:
        issues.append(issue("error", "trace-pattern-empty-applies-to", f"{path}/applies_to",
                            "a trace pattern must apply to at least one entity type"))
    if isinstance(pattern.leaf, DerivedReachabilityLeaf) and pattern.leaf.max_hops > MAX_LEAF_HOPS:
        issues.append(issue("error", "trace-pattern-hops-exceeded", f"{path}/leaf/max_hops",
                            f"leaf max_hops must not exceed {MAX_LEAF_HOPS}"))
    issues.extend(_validate_edge_budget(pattern, patterns, path=path, check_ergonomics=check_ergonomics))
    return issues


def _validate_edge_budget(
    pattern: TracePattern, patterns: TracePatternSet, *, path: str, check_ergonomics: bool
) -> list[ViewpointValidationIssue]:
    try:
        branch_edges = expand_branch_edges(pattern, patterns)
    except TracePatternError as exc:
        return [issue("error", exc.code, f"{path}/branches", str(exc))]
    if not check_ergonomics:
        return []
    total = len(branch_edges) + len(pattern.shortcuts)
    if total > MAX_EDGE_DECLARATIONS:
        return [issue("error", "trace-pattern-edge-count-exceeded", path,
                      f"a pattern declares at most {MAX_EDGE_DECLARATIONS} edges after ref expansion (got {total})")]
    return []


def validate_trace_pattern_types(
    patterns: TracePatternSet,
    *,
    known_entity_types: frozenset[str],
    known_connection_types: frozenset[str],
    path: str,
) -> list[ViewpointValidationIssue]:
    """Registry-aware check: every entity type (``applies_to`` + edge endpoints) and connection
    type a pattern names must exist. Only a pattern's OWN declared edges are checked — a
    ``{ref}`` resolves to another pattern whose edges are validated at its own definition."""
    issues: list[ViewpointValidationIssue] = []
    for index, pattern in enumerate(patterns.patterns):
        item = f"{path}/{index}"
        for entity_type in pattern.applies_to:
            if entity_type not in known_entity_types:
                issues.append(issue("error", "unknown-entity-type", f"{item}/applies_to",
                                    f"trace pattern references unknown entity type {entity_type!r}"))
        edges: list[EdgeDeclaration] = list(pattern.shortcuts)
        if isinstance(pattern.branches, InlineBranches):
            edges.extend(named.edge for named in pattern.branches.edges)
        for edge in edges:
            issues.extend(_check_edge_types(edge, known_entity_types, known_connection_types, item))
        if isinstance(pattern.leaf, DerivedReachabilityLeaf) and pattern.leaf.connection not in known_connection_types:
            issues.append(issue("error", "unknown-connection-type", f"{item}/leaf",
                                f"leaf references unknown connection type {pattern.leaf.connection!r}"))
    return issues


def _check_edge_types(
    edge: EdgeDeclaration, known_entity_types: frozenset[str], known_connection_types: frozenset[str], path: str
) -> list[ViewpointValidationIssue]:
    issues: list[ViewpointValidationIssue] = []
    if edge.connection not in known_connection_types:
        issues.append(issue("error", "unknown-connection-type", path,
                            f"trace edge references unknown connection type {edge.connection!r}"))
    if edge.endpoint_type not in known_entity_types:
        issues.append(issue("error", "unknown-entity-type", path,
                            f"trace edge references unknown endpoint type {edge.endpoint_type!r}"))
    return issues

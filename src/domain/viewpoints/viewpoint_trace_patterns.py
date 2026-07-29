"""Trace-pattern grammar: the closed ``branch-complete-realization`` kind used by
coverage viewpoints to report FULL (universally-quantified) realization across modeled
motivation branches.

Existing viewpoint criteria (``viewpoint_criteria.py``) can band entities by *existential*
incident-connection reachability, but they cannot express what a coverage view needs: a
branch obligation for a node that is *expected but absent* (an outcome with no requirement,
a goal with no outcome). A denominator built only from existing nodes cannot measure a
missing one — so this grammar models branches as canonical TAGGED obligation tuples, some of
which stand for absent nodes.

Pure shapes + constants only. Parsing lives in ``viewpoint_trace_pattern_parsing.py``,
registry-aware validation in ``viewpoint_trace_pattern_validation.py``, and the
branch-complete evaluation semantics in the application layer. Every construct the persisted
YAML, the REST/GUI authoring DTOs, the validator, and the upgrade detector accept is declared
HERE — nothing downstream may introduce a field or variant absent from this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# --- Closed vocabularies ---------------------------------------------------------------

TracePatternKind = Literal["branch-complete-realization"]
EdgeDirection = Literal["incoming", "outgoing"]
DiagnosticStatus = Literal["shortcut", "ambiguous_link"]
LeafTraversal = Literal["direct_and_derived"]
RealizerRegistry = Literal["permitted-realizers-of-requirement"]

VALID_EDGE_DIRECTIONS: frozenset[str] = frozenset({"incoming", "outgoing"})
VALID_DIAGNOSTIC_STATUSES: frozenset[str] = frozenset({"shortcut", "ambiguous_link"})
VALID_LEAF_TRAVERSALS: frozenset[str] = frozenset({"direct_and_derived"})
VALID_REALIZER_REGISTRIES: frozenset[str] = frozenset({"permitted-realizers-of-requirement"})

# --- Structural caps (validated at load) -----------------------------------------------

MAX_TRACE_PATTERNS = 8
MAX_EDGE_DECLARATIONS = 8  # stored + diagnostic edges per pattern, measured AFTER {ref} expansion
MAX_LEAF_HOPS = 4
MAX_REF_EXPANSION_DEPTH = 2
MAX_REFERENCES_PER_DECLARATION = 4

# --- Typed load/validation error codes (stable, closed) --------------------------------

ERR_UNKNOWN_KIND = "trace-pattern-unknown-kind"
ERR_UNKNOWN_FIELD = "trace-pattern-unknown-field"
ERR_UNKNOWN_VARIANT = "trace-pattern-unknown-variant"
ERR_DUPLICATE_NAME = "trace-pattern-duplicate-name"
ERR_DANGLING_REF = "trace-pattern-dangling-ref"
ERR_CYCLIC_REF = "trace-pattern-cyclic-ref"
ERR_TOO_MANY_PATTERNS = "trace-pattern-count-exceeded"
ERR_TOO_MANY_EDGES = "trace-pattern-edge-count-exceeded"
ERR_TOO_MANY_REFS = "trace-pattern-ref-count-exceeded"
ERR_REF_DEPTH = "trace-pattern-ref-depth-exceeded"
ERR_HOPS_EXCEEDED = "trace-pattern-hops-exceeded"
ERR_EMPTY_APPLIES_TO = "trace-pattern-empty-applies-to"
ERR_MISSING_FIELD = "trace-pattern-missing-field"


class TracePatternError(ValueError):
    """A typed grammar error carrying a stable ``code`` (one of the ``ERR_*`` constants).

    Subclasses ``ValueError`` so it composes with the surrounding query parser, which already
    treats malformed declarations as ``ValueError``; the ``code`` lets callers and the upgrade
    detector branch on the specific failure without string-matching messages."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


# --- Edge variants (discriminated by ``kind``) -----------------------------------------


@dataclass(frozen=True)
class StoredEdge:
    """One branch hop over a DIRECT stored connection. Branch enumeration walks stored edges
    only — derived relationships would collapse or bypass the modeled branches this view must
    quantify over."""

    connection: str
    direction: EdgeDirection
    endpoint_type: str
    kind: Literal["stored-edge"] = "stored-edge"


@dataclass(frozen=True)
class DiagnosticEdge:
    """A shortcut/association edge that is *observed and reported* (with ``status``) but never
    counted as a satisfied branch — e.g. a ``requirement —influence→ goal`` shortcut, or a
    generic ``archimate-association`` that yields ``ambiguous_link`` rather than asserted
    realization intent."""

    connection: str
    direction: EdgeDirection
    endpoint_type: str
    status: DiagnosticStatus
    kind: Literal["diagnostic-edge"] = "diagnostic-edge"


EdgeDeclaration = StoredEdge | DiagnosticEdge


# --- Leaf endpoint variants (discriminated by ``kind``) --------------------------------


@dataclass(frozen=True)
class RegistryEndpoint:
    """Leaf target = the registry-derived eligible realizer set for a requirement (the
    requirement type's permitted incoming-realization source types, minus motivation-only
    refiners and junction/grouping helpers). Resolved at load from the module registry."""

    registry: RealizerRegistry
    kind: Literal["registry"] = "registry"


@dataclass(frozen=True)
class LayerMembershipEndpoint:
    """Leaf target = membership in a layer by module-declared ``domain`` (and optional
    ``entity_class``). Used by the verdict-neutral diagnostic columns (behavior/business/
    application)."""

    domain: str
    entity_class: str | None = None  # serialized as ``class``
    kind: Literal["layer"] = "layer"


LeafEndpoint = RegistryEndpoint | LayerMembershipEndpoint


# --- Leaf variants (discriminated by ``kind``) -----------------------------------------


@dataclass(frozen=True)
class NoneLeaf:
    """No leaf reachability — the pattern reports branch completeness only (``motivation``)."""

    kind: Literal["none"] = "none"


@dataclass(frozen=True)
class DerivedReachabilityLeaf:
    """From each terminal requirement obligation, at least one incoming realization chain
    (direct or derived, hop-capped) must reach an element of ``endpoint``."""

    connection: str
    endpoint: LeafEndpoint
    max_hops: int = MAX_LEAF_HOPS
    traversal: LeafTraversal = "direct_and_derived"
    kind: Literal["derived-reachability"] = "derived-reachability"


Leaf = NoneLeaf | DerivedReachabilityLeaf


# --- Branch source variants (discriminated by shape) -----------------------------------


@dataclass(frozen=True)
class NamedBranchEdge:
    """A stored branch hop under an authoring label (declaration order is significant)."""

    label: str
    edge: StoredEdge


@dataclass(frozen=True)
class InlineBranches:
    """Branch edges declared directly on the pattern, as an ordered mapping of label→edge."""

    edges: tuple[NamedBranchEdge, ...]
    kind: Literal["inline"] = "inline"


@dataclass(frozen=True)
class BranchesRef:
    """Immutable value-expansion of another pattern's ``branches`` (same document, acyclic).
    Only the branch edges expand — never the referent's shortcuts, leaf, or status semantics."""

    ref: str
    kind: Literal["ref"] = "ref"


Branches = InlineBranches | BranchesRef


# --- Pattern + set ---------------------------------------------------------------------


@dataclass(frozen=True)
class TracePattern:
    """One coverage pattern of the closed ``branch-complete-realization`` kind. Branch
    quantification (universal over branches, existential at the leaf) is FIXED behavior of the
    kind, not authorable — there are no step/alternative/quantifier keywords."""

    name: str
    applies_to: tuple[str, ...]
    branches: Branches
    shortcuts: tuple[DiagnosticEdge, ...] = ()
    leaf: Leaf = NoneLeaf()
    diagnostic: bool = False
    kind: TracePatternKind = "branch-complete-realization"

    @property
    def role(self) -> Literal["authoritative", "diagnostic"]:
        """A ``diagnostic`` pattern is verdict-neutral (``none_observed`` on absence, never a
        gap); its result is a DiagnosticPatternResult. Every other pattern is authoritative."""
        return "diagnostic" if self.diagnostic else "authoritative"


@dataclass(frozen=True)
class TracePatternSet:
    """The ordered, name-unique collection of a viewpoint's trace patterns (aggregate root for
    ref resolution and cap enforcement)."""

    patterns: tuple[TracePattern, ...] = ()

    def by_name(self, name: str) -> TracePattern | None:
        return next((p for p in self.patterns if p.name == name), None)

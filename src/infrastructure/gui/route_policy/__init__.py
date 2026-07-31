"""The REST route-policy manifest: one row per canonical operation, and the lookups over it.

Four registries used to each hold their own copy of a route path — the decorator, the mutation
manifest, the ``authorized_write`` call inside every handler, and the conditional-read
allowlist. Equality between any two of them can hold while a third is stale, and a stale
authorization tuple fails the live write closed with nothing red in the suite. The fix is to
have one place where an operation's address is written down and to derive the rest:

* handlers name an **operation id** and let :func:`route_key` supply ``(METHOD, template)``;
* the conditional-read middleware asks for :data:`CONDITIONAL_READ_TEMPLATES`;
* the client and dev proxy consume :func:`timeout_class_templates`;
* the fitness functions compare the manifest against the generated OpenAPI document, which is
  an oracle the manifest does not produce.

The manifest is *canonical*, not *current*: during the migration ``_pending`` enumerates what
is still served under its old address and what is not served yet.
"""

from __future__ import annotations

from src.infrastructure.gui.route_policy._assurance import (
    ANALYSIS_ROWS,
    NODE_ROWS,
    SIGNAL_ROWS,
    STORE_ROWS,
)
from src.infrastructure.gui.route_policy._authoring import (
    DOCUMENT_ROWS,
    GROUP_ROWS,
    VIEWPOINT_ROWS,
)
from src.infrastructure.gui.route_policy._diagrams import (
    DIAGRAM_ROWS,
    DIAGRAM_TYPE_ROWS,
    MATRIX_ROWS,
)
from src.infrastructure.gui.route_policy._entities import (
    CONNECTION_ROWS,
    ENTITY_ROWS,
    SEARCH_ROWS,
    TAXONOMY_ROWS,
)
from src.infrastructure.gui.route_policy._pending import (
    RETIRED_ROUTES,
    UNSERVED_OPERATIONS,
)
from src.infrastructure.gui.route_policy._platform import ADMIN_ROWS, PROMOTION_ROWS, SYNC_ROWS
from src.infrastructure.gui.route_policy._response_contracts import UNTYPED_RESPONSE_OPERATIONS
from src.infrastructure.gui.route_policy._types import (
    BODYLESS,
    MEDIA,
    MUTATION_METHODS,
    RESPONSE_KINDS,
    STREAM,
    CacheDirective,
    ConditionalRead,
    MutationDomain,
    ResourceKind,
    RoutePolicyError,
    RouteRow,
    TimeoutClass,
    path_parameters,
)

ROUTE_POLICY: tuple[RouteRow, ...] = (
    *ENTITY_ROWS,
    *CONNECTION_ROWS,
    *SEARCH_ROWS,
    *TAXONOMY_ROWS,
    *DIAGRAM_ROWS,
    *MATRIX_ROWS,
    *DIAGRAM_TYPE_ROWS,
    *DOCUMENT_ROWS,
    *GROUP_ROWS,
    *VIEWPOINT_ROWS,
    *SYNC_ROWS,
    *PROMOTION_ROWS,
    *ADMIN_ROWS,
    *ANALYSIS_ROWS,
    *NODE_ROWS,
    *STORE_ROWS,
    *SIGNAL_ROWS,
)


def _index_by_operation(rows: tuple[RouteRow, ...]) -> dict[str, RouteRow]:
    index: dict[str, RouteRow] = {}
    for row in rows:
        if row.operation_id in index:
            raise RoutePolicyError(f"duplicate operation id {row.operation_id!r}")
        index[row.operation_id] = row
    return index


def _index_by_key(rows: tuple[RouteRow, ...]) -> dict[tuple[str, str], RouteRow]:
    index: dict[tuple[str, str], RouteRow] = {}
    for row in rows:
        if row.key in index:
            raise RoutePolicyError(f"duplicate route key {row.key!r}")
        index[row.key] = row
    return index


BY_OPERATION: dict[str, RouteRow] = _index_by_operation(ROUTE_POLICY)
BY_KEY: dict[tuple[str, str], RouteRow] = _index_by_key(ROUTE_POLICY)


def row_for(operation_id: str) -> RouteRow:
    """The manifest row for an operation, or ``LookupError`` — never a silent default.

    Called on the request path by ``authorized_write``, so an operation that was renamed
    without its manifest row moving fails immediately and visibly rather than executing an
    unclassified write.
    """
    row = BY_OPERATION.get(operation_id)
    if row is None:
        raise LookupError(
            f"No route-policy row for operation {operation_id!r} — declare the operation in the "
            "route-policy manifest before serving it."
        )
    return row


def route_key(operation_id: str) -> tuple[str, str]:
    """The ``(METHOD, template)`` pair for an operation. The single source of that pair."""
    return row_for(operation_id).key


def templates_for(*, mutation_domain: MutationDomain) -> frozenset[tuple[str, str]]:
    """Route keys whose writes belong to one policy domain."""
    return frozenset(row.key for row in ROUTE_POLICY if row.mutation_domain == mutation_domain)


def timeout_class_templates(timeout_class: TimeoutClass) -> frozenset[str]:
    """Route templates in one timeout class, for the client and the dev-proxy check."""
    return frozenset(row.template for row in ROUTE_POLICY if row.timeout_class == timeout_class)


def _parameterless_shape(template: str) -> str:
    """A template with every parameter name erased, so two spellings of one path compare equal."""
    return "/".join(
        "{}" if segment.startswith("{") and segment.endswith("}") else segment
        for segment in template.split("/")
    )


#: Path shapes something still answers to. The canonical templates, and only those: no retired
#: address is mounted any more, which the addressing fitness function asserts directly.
_LIVE_SHAPES: frozenset[str] = frozenset(
    _parameterless_shape(row.template) for row in ROUTE_POLICY
)

#: Path literals no longer served anywhere, so no longer permitted in runtime source, current
#: documentation, examples or positive tests.
#:
#: Two exclusions, both because the literal is not *observable* as retired by a path scan:
#:
#: * a path stays permitted while any method on it is still mounted, and a collection path can
#:   carry several;
#: * a rename that only changes a **parameter name** — ``/api/diagram-types/{name}/entity-types``
#:   to ``…/{diagram_type}/…`` — leaves exactly the same concrete URLs, so no scan over paths can
#:   tell the two apart. That rename is real, and it *is* checked: the inventory equality compares
#:   templates exactly. Asserting it here would only produce a false positive on its own
#:   replacement.
RETIRED_PATH_LITERALS: frozenset[str] = frozenset(
    template
    for _method, template in RETIRED_ROUTES
    if _parameterless_shape(template) not in _LIVE_SHAPES
)


def reserved_segments_under(collection_template: str) -> frozenset[str]:
    """Literal segments the manifest mounts directly under a collection.

    An identifier equal to one of these cannot be addressed: the literal route is registered first
    and matched first, so the URL would name a different resource than the caller meant —
    ``/api/viewpoints/pins`` is the pin list, never a viewpoint called ``pins``. Derived from the
    manifest rather than listed by hand, so declaring a new sibling protects the identifier space
    in the same edit.
    """
    prefix = collection_template.rstrip("/") + "/"
    segments = set()
    for row in ROUTE_POLICY:
        if not row.template.startswith(prefix):
            continue
        segment = row.template[len(prefix) :].split("/")[0]
        if not (segment.startswith("{") and segment.endswith("}")):
            segments.add(segment)
    return frozenset(segments)


#: Canonical templates eligible for ETag revalidation — the *decision*.
CONDITIONAL_READ_TEMPLATES: frozenset[str] = frozenset(
    row.template for row in ROUTE_POLICY if row.conditional_read == "etag"
)


def served_templates_for(operation_id: str) -> frozenset[str]:
    """The templates an operation is reachable at today: its legacy ones, or its canonical one.

    One template per operation, now that every address has moved. This used to consult the
    migration ledger first, because a policy keyed on an address has to follow that address: a
    cache-eligible read whose rename was still pending would otherwise have lost its ETag the moment
    the manifest named its new template, silently. Nothing is pending, so there is nothing to
    consult — and an operation the manifest declares but does not serve yields no template rather
    than a wrong one.
    """
    if operation_id in UNSERVED_OPERATIONS:
        return frozenset()
    return frozenset({BY_OPERATION[operation_id].template})


#: Templates the conditional-read middleware matches *today* — canonical where the rename has
#: landed, legacy where it has not.
SERVED_CONDITIONAL_READ_TEMPLATES: frozenset[str] = frozenset(
    template
    for row in ROUTE_POLICY
    if row.conditional_read == "etag"
    for template in served_templates_for(row.operation_id)
)

#: Write-shaped operations that mutate nothing: previews, plans, query execution, exports.
NON_MUTATING_WRITE_SHAPED: frozenset[tuple[str, str]] = frozenset(
    row.key for row in ROUTE_POLICY if row.is_write_shaped and row.mutation_domain == "none"
)

__all__ = [
    "BODYLESS",
    "BY_KEY",
    "BY_OPERATION",
    "CONDITIONAL_READ_TEMPLATES",
    "MEDIA",
    "RESPONSE_KINDS",
    "MUTATION_METHODS",
    "NON_MUTATING_WRITE_SHAPED",
    "RETIRED_PATH_LITERALS",
    "RETIRED_ROUTES",
    "ROUTE_POLICY",
    "SERVED_CONDITIONAL_READ_TEMPLATES",
    "STREAM",
    "UNSERVED_OPERATIONS",
    "UNTYPED_RESPONSE_OPERATIONS",
    "CacheDirective",
    "ConditionalRead",
    "MutationDomain",
    "ResourceKind",
    "RoutePolicyError",
    "RouteRow",
    "TimeoutClass",
    "path_parameters",
    "reserved_segments_under",
    "route_key",
    "row_for",
    "served_templates_for",
    "templates_for",
    "timeout_class_templates",
]

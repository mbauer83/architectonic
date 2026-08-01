"""Bridging helpers between the canonical route-policy manifest and the served surface.

The manifest states where an operation *belongs*; during the migration some operations are
still mounted where they *were*. Only the fitness functions need to know the difference, and
only until the allowlists in ``route_policy._pending`` are empty — so the knowledge lives
here, in test support, rather than in the runtime package where it would make production code
aware of its own migration state.
"""

from __future__ import annotations

from src.infrastructure.backend.arch_backend_app import _build_app
from src.infrastructure.rest.route_policy import (
    ROUTE_POLICY,
    UNSERVED_OPERATIONS,
    RouteRow,
)

RouteKey = tuple[str, str]


def served_route_keys() -> frozenset[RouteKey]:
    """Every ``(METHOD, template)`` the built application serves, from its OpenAPI document.

    Read from ``openapi()`` rather than ``app.routes``: included routers are lazy wrappers
    that are never flattened, so walking ``app.routes`` sees 13 of the 161 operations.
    """
    paths = _build_app().openapi().get("paths", {})
    return frozenset(
        (method.upper(), path) for path, operations in paths.items() for method in operations
    )


def effective_route_keys(row: RouteRow) -> frozenset[RouteKey]:
    """The addresses *row*'s operation is reachable at today.

    Its canonical address, and **nothing** while it is declared unserved — an operation the manifest
    declares but does not mount cannot appear in a registry keyed by served routes. This used to add
    the legacy addresses an operation was still mounted at; the migration is over, so there are
    none.
    """
    if row.operation_id in UNSERVED_OPERATIONS:
        return frozenset()
    return frozenset({row.key})


def effective_keys_for(
    *, mutation_domain: str, template_prefix: str | None = None, exclude_prefix: str | None = None
) -> frozenset[RouteKey]:
    """Today's addresses of every manifest row in one mutation domain.

    ``template_prefix``/``exclude_prefix`` scope the answer by canonical surface, because the
    registries this is compared against are themselves prefix-scoped: the architecture
    mutation manifest excludes ``/api/assurance`` by design.
    """
    return frozenset(
        key
        for row in ROUTE_POLICY
        if row.mutation_domain == mutation_domain
        and (template_prefix is None or row.template.startswith(template_prefix))
        and (exclude_prefix is None or not row.template.startswith(exclude_prefix))
        for key in effective_route_keys(row)
    )


def effective_non_mutating_write_shaped(*, exclude_prefix: str | None = None) -> frozenset[RouteKey]:
    """Today's addresses of the write-shaped operations declared to mutate nothing."""
    return frozenset(
        key
        for row in ROUTE_POLICY
        if row.is_write_shaped
        and row.mutation_domain == "none"
        and (exclude_prefix is None or not row.template.startswith(exclude_prefix))
        for key in effective_route_keys(row)
    )

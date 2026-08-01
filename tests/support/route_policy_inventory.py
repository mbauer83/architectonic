"""Bridging helpers between the canonical route-policy manifest and the served surface.

Reading the served surface is the part that needs the application built, and it belongs here rather
than in the runtime package: production code has no business knowing which of its own addresses a
fitness function is checking. The manifest is now the whole answer — an operation's canonical address
*is* the one it is served at — so what is left is the reading, not a reconciliation.
"""

from __future__ import annotations

from src.infrastructure.backend.arch_backend_app import _build_app
from src.infrastructure.rest.route_policy import ROUTE_POLICY

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
        for key in (row.key,)
    )


def effective_non_mutating_write_shaped(*, exclude_prefix: str | None = None) -> frozenset[RouteKey]:
    """Today's addresses of the write-shaped operations declared to mutate nothing."""
    return frozenset(
        key
        for row in ROUTE_POLICY
        if row.is_write_shaped
        and row.mutation_domain == "none"
        and (exclude_prefix is None or not row.template.startswith(exclude_prefix))
        for key in (row.key,)
    )

"""Operation ids for the generated OpenAPI document, taken from the route-policy manifest.

FastAPI's default id is the handler's function name with the path mangled onto it —
``read_entity_api_entity_get``. Two things are wrong with that for a published contract. It leaks
an implementation detail (rename the function, break the client), and it *contains the path*, so
every route this migration renames would rename its operation id too. Since the TypeScript
generator keys its output by operation id, that would rewrite the whole generated surface for a
change that is not supposed to alter a single payload.

So the id comes from the manifest, where it is declared as ``{tag}_{verb}_{resource}`` and is
stable across the rename: a legacy address and its canonical replacement resolve to the *same*
operation id, which is what lets the generated types stay still while the routes move.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.infrastructure.rest.route_policy import BY_KEY

if TYPE_CHECKING:
    from fastapi.routing import APIRoute


def manifest_operation_id(route: "APIRoute") -> str:
    """The manifest's operation id for a route, or FastAPI's default when it has no row.

    A route without a row is either excluded from the schema (the health probe) or a defect the
    inventory fitness function reports; falling back keeps document generation working while that
    test — not this function — is the thing that fails.

    This used to consult the migration ledger when a key had no row, and to hand back FastAPI's
    default for the four completeness endpoints that were collapsing into one operation — an id has
    to be unique in an OpenAPI document, and four addresses could not all claim the canonical one.
    Both are gone with the migration: every served address has a row, and no operation answers at
    more than one address.
    """
    for method in sorted(route.methods or set()):
        row = BY_KEY.get((method, route.path))
        if row is not None:
            return row.operation_id
    return _fastapi_default(route)


def _fastapi_default(route: "APIRoute") -> str:
    from fastapi.routing import generate_unique_id  # noqa: PLC0415

    return generate_unique_id(route)

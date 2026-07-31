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

from collections import Counter
from typing import TYPE_CHECKING

from src.infrastructure.gui.route_policy import BY_KEY, LEGACY_ROUTES

if TYPE_CHECKING:
    from fastapi.routing import APIRoute


def _multi_address_operations() -> frozenset[str]:
    """Operations still reachable at more than one address, so not yet uniquely nameable.

    Four method-specific completeness endpoints collapse into one operation. Until they do, all
    four are mounted, and an operation id is required to be unique in an OpenAPI document — so
    none of them may claim the canonical id yet. There is no stable id for four routes becoming
    one, which is exactly why this is temporary rather than a naming decision.
    """
    counts = Counter(LEGACY_ROUTES.values())
    return frozenset(operation for operation, count in counts.items() if count > 1)


_MULTI_ADDRESS = _multi_address_operations()


def manifest_operation_id(route: "APIRoute") -> str:
    """The manifest's operation id for a route, or FastAPI's default when it has no row.

    A route without a row is either excluded from the schema (the health probe) or a defect the
    inventory fitness function reports; falling back keeps document generation working while that
    test — not this function — is the thing that fails.
    """
    for method in sorted(route.methods or set()):
        key = (method, route.path)
        row = BY_KEY.get(key)
        operation = row.operation_id if row is not None else LEGACY_ROUTES.get(key)
        if operation is None:
            continue
        return _fastapi_default(route) if operation in _MULTI_ADDRESS else operation
    return _fastapi_default(route)


def _fastapi_default(route: "APIRoute") -> str:
    from fastapi.routing import generate_unique_id  # noqa: PLC0415

    return generate_unique_id(route)

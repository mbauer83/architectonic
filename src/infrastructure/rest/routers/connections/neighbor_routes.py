"""The neighbourhood of a record: an entity's, and a construct a diagram owns, at its diagram's address.

Its own module so the connection read routes stay within the module-size limit in `STD@1777137196`.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.artifact_id import held_record_id
from src.infrastructure.derived_neighbors import DerivationLimitError, derive_neighbors
from src.infrastructure.rest.contracts.entities import EntityNeighborhoodResponse
from src.infrastructure.rest.dependencies import runtime_catalogs_dependency
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._failures import derivation_limit
from src.infrastructure.rest.routers._openapi import READ_RESPONSES, TAG_CONNECTIONS


def register_neighbor_routes(router: APIRouter) -> None:
    """Attach the two addresses of one reading: a record's neighbourhood."""

    @router.get("/api/entities/{artifact_id}/neighbors", tags=[TAG_CONNECTIONS],
        summary="Neighbouring entities of an entity",
        response_model=EntityNeighborhoodResponse, responses=READ_RESPONSES)
    def get_neighbors(
        artifact_id: str,
        max_hops: int | None = None,
        traversal: Literal["direct", "derived"] = "direct",
        include_potential: bool = False,
        catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
    ) -> dict[str, object]:
        """The neighbourhood of one entity, tagged by how it was reached.

        ``traversal`` is an alternate execution specification, so it stays in the query — but the
        two answers are genuinely different shapes, and the direct arm used to carry no tag at all,
        so a client could not tell which it had received.

        ``max_hops`` left unset is one hop for the direct arm and the configured derivation bound for
        the derived one, which composes nothing within fewer than two.
        """
        return _neighbourhood(artifact_id, max_hops, traversal, include_potential=include_potential,
                              catalogs=catalogs)

    @router.get("/api/diagrams/{artifact_id}/entities/{entity_type}/{local_id}/neighbors",
        tags=[TAG_CONNECTIONS], summary="Neighbouring entities of a construct a diagram owns",
        response_model=EntityNeighborhoodResponse, responses=READ_RESPONSES)
    def get_held_record_neighbors(
        artifact_id: str,
        entity_type: str,
        local_id: str,
        max_hops: int | None = None,
        traversal: Literal["direct", "derived"] = "direct",
        include_potential: bool = False,
        catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
    ) -> dict[str, object]:
        """The neighbourhood of a construct a diagram owns — a GSN goal, a swimlane — at its diagram's address.

        The same reading as an entity's: such a construct is a record with connections, but its id
        (``{diagram}#{entity_type}/{local_id}``) holds a slash, which no single path segment can carry,
        so it is addressed in the diagram's segments as its own read is.
        """
        return _neighbourhood(held_record_id(artifact_id, entity_type, local_id), max_hops, traversal,
                              include_potential=include_potential, catalogs=catalogs)


def _neighbourhood(
    entity_id: str,
    max_hops: int | None,
    traversal: Literal["direct", "derived"],
    *,
    include_potential: bool,
    catalogs: RuntimeCatalogs,
) -> dict[str, object]:
    """One record's neighbourhood, directly or by derivation; 404 for a record the model does not hold."""
    repo = s.get_repo()
    if repo.get_entity(entity_id) is None:
        # Identity is in the path now, so an unknown id is an unaddressable resource rather
        # than a filter that matched nothing — and an empty neighbourhood is indistinguishable
        # from a real one with no neighbours, which is the wrong answer to give.
        raise HTTPException(404, f"Not found: {entity_id!r}")
    if traversal == "direct":
        hops = repo.find_neighbors(entity_id, max_hops=max_hops or 1)
        return {"traversal": "direct", "hops": {hop: sorted(ids) for hop, ids in hops.items()}}
    try:
        neighbors = derive_neighbors(
            entity_id,
            max_hops=max_hops,
            include_potential=include_potential,
            read_access=repo,
            registries=catalogs.module_catalog,
        )
        return {"traversal": "derived", "neighbors": neighbors}
    except DerivationLimitError as exc:
        raise derivation_limit(str(exc)) from exc

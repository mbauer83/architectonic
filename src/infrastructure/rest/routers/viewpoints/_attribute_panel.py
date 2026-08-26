"""One diagram's attribute panel, as the reading surface serialises it.

Its own module for the reason `_search_hits.py` is one: a router holds what a request handler reaches
for, and this is a mapping from a domain answer to display fields. It has one arm per offered facet, so
it grows whenever the panel learns a new one — and it grew `viewpoints/router.py` past the
source-length policy doing exactly that, on the commit that introduced it.

The keys are the wire contract's, which is `DiagramAttributePanelResponse`. Nothing is decided here:
which attributes are offered, what each is declared to be and which can take a colour are the
application layer's answers, and this turns them into JSON.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.viewpoints.diagram_attribute_panel import AttributeOffer, DiagramAttributeOffers
from src.infrastructure.rest.contracts.viewpoint_projection import DiagramAttributePanelResponse
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._openapi import READ_RESPONSES, TAG_VIEWPOINTS
from src.infrastructure.rest.routers.viewpoints._freshness import (
    fresh_viewpoints_runtime_catalogs_dependency,
)


def _attribute_to_dict(attribute: AttributeOffer) -> dict[str, Any]:
    return {
        "name": attribute.name,
        "declared_type": attribute.declared_type,
        "colour": attribute.colour,
        "values": list(attribute.values),
        "present_on": attribute.present_on,
    }


def attribute_panel_to_dict(offers: DiagramAttributeOffers, *, can_explain: bool) -> dict[str, Any]:
    """The whole panel: what reads across the diagram, then one entry per (type, specialization).

    The order is the application layer's and is preserved rather than re-sorted here — it sorts so the
    answer is stable, and a second sort at the edge would be a second opinion about it.
    """
    return {
        "drawn": offers.drawn,
        "shared": [
            {"attribute": _attribute_to_dict(offer.attribute), "on_rows": list(offer.on_rows)}
            for offer in offers.shared
        ],
        "disputed": list(offers.disputed),
        "can_explain_notation": can_explain,
        "types": [
            {
                "entity_type": offer.entity_type,
                "specialization": offer.specialization,
                "drawn": offer.drawn,
                "attributes": [_attribute_to_dict(attribute) for attribute in offer.attributes],
            }
            for offer in offers.types
        ],
    }


def _can_explain(diag_rec: Any, repo_root: Path, catalogs: RuntimeCatalogs) -> bool:
    """Whether a legend for this diagram would say anything.

    Asked here so the surface can withhold the control rather than offer one that does nothing: a
    diagram with no stereotypes, no glyphs and no relationships has no notation to explain, and a
    reader cannot tell a legend that says nothing from one that failed.

    Read from the body, because the body's preamble is what the renderer is handed — the same reason
    the legend itself reads it there rather than deriving it from today's ontology.
    """
    from src.application.viewpoints.placed_occurrences import resolve_placed_connections  # noqa: PLC0415
    from src.infrastructure.rendering.diagram_legend_for_reading import (  # noqa: PLC0415
        can_explain_notation,
        notation_in_use,
    )
    from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file  # noqa: PLC0415

    if not diag_rec.path.exists():
        return False
    _, registry, _ = s.get_write_deps(catalogs)
    notation = notation_in_use(
        [c.conn_type for c in resolve_placed_connections(dict(diag_rec.extra), registry)],
        repo_root=repo_root,
        relation_notations=catalogs.connections.all_relation_notations(),
    )
    return can_explain_notation(
        parse_diagram_file(diag_rec.path).puml_body,
        declarations=notation.declarations,
        connection_notations=notation.connection_notations,
    )


def register_attribute_panel_route(router: APIRouter) -> None:
    @router.get("/api/diagrams/{artifact_id}/attribute-panel", tags=[TAG_VIEWPOINTS],
        summary="What a diagram's entities can be coloured by and print", response_model=DiagramAttributePanelResponse,
        responses=READ_RESPONSES)
    def get_diagram_attribute_panel(
        artifact_id: str,
        catalogs: RuntimeCatalogs = Depends(fresh_viewpoints_runtime_catalogs_dependency),
    ) -> dict[str, object]:
        """The reading panel for one diagram: its types, and what their attributes allow.

        Assembled by the application layer, not here. This resolves the diagram, hands over the entities
        it places and the catalogues that know what a type declares, and serialises the answer — the same
        division the projection route keeps, and for the reason cycle 3's survey gives: a domain rule
        assembled in a router is a second assembly of it.
        """
        from src.application.viewpoints.diagram_attribute_panel import offers_for_diagram  # noqa: PLC0415
        from src.application.viewpoints.placed_occurrences import resolve_placed_entities  # noqa: PLC0415

        repo = s.get_repo()
        diag_rec = repo.get_diagram(artifact_id)
        if diag_rec is None:
            raise HTTPException(404, f"Diagram not found: {artifact_id!r}")
        repo_root = s.maybe_engagement_root()
        if repo_root is None:
            raise HTTPException(500, "Repository not initialized")
        _, registry, _ = s.get_write_deps(catalogs)
        offers = offers_for_diagram(
            resolve_placed_entities(dict(diag_rec.extra), registry),
            repo_root,
            specialization_catalog=catalogs.specializations,
            profile_registry=catalogs.profiles,
        )
        return attribute_panel_to_dict(offers, can_explain=_can_explain(diag_rec, repo_root, catalogs))

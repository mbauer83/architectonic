"""Which entity and connection types a diagram kind will accept — the authoring palette.

A pure composition of the diagram-type catalogue, the ontology's domain order, and an optional
narrowing scope. It lived in `rest/routers/diagrams/_context.py`, which is where it was first needed
rather than where it belongs: nothing here touches a request, a repository or a file, and two callers
outside REST want the same answer.

**Why it moved.** `GET /api/diagram-types/{t}/entity-types` and its connection twin are the only
address on the whole surface that answers "which *types* may this diagram hold" — `/api/diagram-types`
gives labels, `ui-config` gives rendering hints, and authoring guidance gave accepted *domains* and
prose. An agent asking `artifact_authoring_guidance(diagram_type=X)` was therefore told the domains and
left to reconstruct the type list itself, which is the same derivation done less well and without the
narrowing. Both now read from here, so the two transports cannot answer differently — the failure the
four `search_nodes` implementations had, caught before it happened rather than after.

**The scope arrives resolved, not as a slug.** REST turns a `?viewpoint=` slug into a `ConceptScope`
and answers 404 when it names nothing, which is an HTTP decision and stays in the router. This module
takes the scope it is given, so it has no opinion about how a caller chose one — and a caller with no
viewpoint passes nothing.
"""

from __future__ import annotations

from typing import Any

from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.concept_scope import ConceptScope

#: Sorted after every non-ordered domain, so an unrecognised one is visibly last rather than first.
_UNORDERED_DOMAIN_RANK = 99


def diagram_kind_entity_types(
    diagram_type: str, catalogs: RuntimeCatalogs, *, scope: ConceptScope | None = None
) -> list[dict[str, Any]]:
    """The entity types this diagram kind accepts, in the ontology's domain order.

    Internal types are omitted: they exist to make the ontology work and are not things an author
    places. A `scope` narrows further — the effective authoring scope is the diagram type's own
    intersected with a chosen viewpoint's.
    """
    kind = catalogs.diagram_types.get_diagram_type(diagram_type)
    ordered_domains = catalogs.ontology.domain_order()
    items = [
        {
            "artifact_type": artifact_type,
            "prefix": info.prefix,
            "domain": info.hierarchy[0] if info.hierarchy else "",
            "classes": list(info.classes),
        }
        for artifact_type, info in kind.effective_entity_types().items()
        if not info.internal and (scope is None or scope.admits_entity_type(artifact_type, info))
    ]
    items.sort(
        key=lambda item: (
            ordered_domains.index(str(item["domain"]))
            if item["domain"] in ordered_domains
            else _UNORDERED_DOMAIN_RANK,
            item["artifact_type"],
        )
    )
    return items


def diagram_kind_connection_types(
    diagram_type: str, catalogs: RuntimeCatalogs, *, scope: ConceptScope | None = None
) -> list[dict[str, Any]]:
    """The connection types this diagram kind accepts, by name.

    Name order rather than domain order: a connection type has no domain of its own, and its language
    (`conn_lang`) groups it well enough that alphabetical is the readable choice.
    """
    kind = catalogs.diagram_types.get_diagram_type(diagram_type)
    items = [
        {
            "connection_type": connection_type,
            "conn_lang": info.conn_lang,
            "symmetric": info.symmetric,
            "classes": list(info.classes),
        }
        for connection_type, info in kind.effective_connection_types().items()
        if scope is None or scope.admits_connection_type(connection_type)
    ]
    items.sort(key=lambda item: item["connection_type"])
    return items

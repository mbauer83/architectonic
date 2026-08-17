"""The deployment axis: where one system's containers run.

Beside `_projection.py` rather than inside it, because this is the *other* axis and the shape says
so — the containment projections walk one root down through nesting, and this one walks the
two-hop path from a container out to the technology that holds its artifact. It also keeps that
module inside the file-length policy, which the two axes together broke.
"""

from __future__ import annotations

from src.diagram_types.c4._projection_rollup import descendants, direct_conns
from src.diagram_types.c4._projection_vocabulary import (
    CONTAINER_INTERNAL_TYPES,
    DEPLOYMENT_TYPE,
    NEIGHBOR_TYPES,
    NESTING_TYPES,
    C4ProjectedItem,
    C4Projection,
    entity_type,
    make_item,
)
from src.domain.relationships.derivation_types import ModelQuery

#: What can host something, at the technology layer. ArchiMate has no relation from a node to an
#: application component — the deployment fact is the two-hop `node -aggregation-> artifact
#: -realization-> component`, which is what `connections.yaml` permits and what this walks.
_DEPLOYMENT_HOST_TYPES: frozenset[str] = frozenset({
    "technology-node", "device", "system-software", "facility", "equipment",
})
_HOSTING_TYPES: frozenset[str] = frozenset({"archimate-composition", "archimate-aggregation"})


def _hosts_of(container_id: str, query: ModelQuery) -> set[str]:
    """Which technology elements a container runs on, along ArchiMate's own deployment path.

    `node -aggregation-> artifact -realization-> component` is the chain the spec defines and the
    only one `connections.yaml` permits, so it is the only one read. A container with no artifact
    is simply undeployed, and saying so by drawing nothing is more honest than inventing a host.
    """
    hosts: set[str] = set()
    for realization in query.find_connections_for(container_id, direction="inbound"):
        if realization.conn_type != "archimate-realization":
            continue
        artifact_id = realization.source
        if entity_type(artifact_id, query) != "artifact":
            continue
        for holds in query.find_connections_for(artifact_id, direction="inbound"):
            if holds.conn_type in _HOSTING_TYPES and entity_type(holds.source, query) in _DEPLOYMENT_HOST_TYPES:
                hosts.add(holds.source)
    return hosts


def _enclosing_nodes(hosts: set[str], query: ModelQuery) -> dict[str, str]:
    """Which node each host sits inside, following the chain as far as the model states it.

    ArchiMate says containment between technology nodes with composition or aggregation — the
    general `@all -> @same` rule permits it — so a container runtime declared inside a machine is a
    fact the model can already hold. Reading only a container's immediate host drew every deployment
    as one flat box, which says the containers run side by side on a machine rather than together
    inside one runtime.

    The walk stops on a repeat, because a containment cycle is a modelling error rather than a
    reason to loop.
    """
    parents: dict[str, str] = {}
    frontier = set(hosts)
    while frontier:
        nxt: set[str] = set()
        for node in sorted(frontier):
            for holds in query.find_connections_for(node, direction="inbound"):
                if holds.conn_type not in _HOSTING_TYPES:
                    continue
                if entity_type(holds.source, query) not in _DEPLOYMENT_HOST_TYPES:
                    continue
                if node in parents or holds.source == node:
                    continue
                parents[node] = holds.source
                if holds.source not in parents and holds.source not in hosts:
                    nxt.add(holds.source)
        frontier = nxt - set(parents)
    return parents


def project_c4_deployment(
    root_entity_id: str,
    query: ModelQuery,
    *,
    internal_c4_type: str,
    scope_entity_type: str,
    person_archimate_types: frozenset[str],
) -> C4Projection:
    """Where one system's containers run: the technology elements that host them.

    The second axis rather than a fourth level. It draws the *same* containers a container view
    draws, placed on the nodes that hold their artifacts, so it sits beside that view rather than
    below it — which is why it has no entry in `_C4_LEVELS`.
    """
    def make(eid: str, role: str, item_type: str) -> C4ProjectedItem:
        return make_item(eid, role, scope_entity_type, item_type, person_archimate_types, query)

    containers = {
        eid for eid in descendants(root_entity_id, query, nesting_types=NESTING_TYPES, max_depth=1)
        if entity_type(eid, query) in CONTAINER_INTERNAL_TYPES
    }
    hosted: dict[str, set[str]] = {cid: _hosts_of(cid, query) for cid in sorted(containers)}
    direct_hosts = {host for host_set in hosted.values() for host in host_set}
    #: Where each host itself sits. A deployment is nested in reality — a container runtime on a
    #: machine — and reading only the immediate host flattened that into "side by side on a box".
    enclosing = _enclosing_nodes(direct_hosts, query)
    hosts = direct_hosts | set(enclosing.values())

    host_items = tuple(make(eid, "internal", "node") for eid in sorted(hosts))
    container_items = tuple(
        make(cid, "internal", internal_c4_type) for cid, host_set in sorted(hosted.items()) if host_set
    )
    drawn = hosts | {item.entity_id for item in container_items}
    return C4Projection(
        diagram_type=DEPLOYMENT_TYPE,
        items=(make(root_entity_id, "scope", scope_entity_type), *host_items, *container_items),
        connection_ids=tuple(sorted(direct_conns(drawn, query, dependency_types=NEIGHBOR_TYPES))),
        contained_by=tuple(
            [
                (cid, host)
                for cid, host_set in sorted(hosted.items())
                for host in sorted(host_set)[:1]  # one drawn home per container; a second duplicates it
            ]
            + sorted(enclosing.items())
        ),
    )

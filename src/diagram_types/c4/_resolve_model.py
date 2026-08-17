"""C4 model-backed state resolution (ArchiMate graph → C4 items/connections)."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path

from src.diagram_types.c4._c4_types import (
    _alias_for,
    _C4Connection,
    _conn_label,
    _normalize_alias,
    _ResolvedItem,
    _ResolvedState,
)
from src.diagram_types.c4._projection_vocabulary import is_externally_styled
from src.domain.diagrams.bindings import EXCLUDED_IDS_KEY, INCLUDED_IDS_KEY
from src.domain.diagrams.diagram_selection import DiagramSelectionError
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.relationships.derivation_types import ModelQuery

#: A trailing version specifier on an authored technology entry — `>=3.13`, `(standard)` and the
#: like. Dropped so the box reads at a glance; the version is a fact about the dependency rather
#: than about what the container is.
_VERSION_SPEC_RE = re.compile(r"\s*(?:[<>=~!]=?|\().*$")


def _short_description(entity: EntityRecord | None) -> str:
    """First prose sentence of the entity's body, ≤100 chars — the C4 element role line.

    Skips the leading ``## Name`` heading and any table/properties blocks; returns the
    first real paragraph's opening sentence so C4 persons carry a short role description.
    """
    text = entity.content_text if entity is not None else ""
    if not text:
        return ""
    for block in text.split("\n\n"):
        line = block.strip().splitlines()[0].strip() if block.strip() else ""
        if not line or line.startswith(("#", "|", "-", "*", ">")):
            continue
        sentence = line.split(". ")[0].rstrip(".")
        return sentence if len(sentence) <= 100 else sentence[:99].rstrip() + "…"
    return ""


#: The specialization by which the model states that a component is a store rather than software
#: acting on one. Declared in the ontology, so a view draws a store as a store without inferring it.
_DATA_STORE_SPECIALIZATION = "data-store"


def _is_store(entity: EntityRecord | None) -> bool:
    return entity is not None and _DATA_STORE_SPECIALIZATION in entity.specializations


def _item_from_entity(
    entity: EntityRecord | None, entity_id: str, item_type: str, *, external: bool, technology: str = ""
) -> _ResolvedItem:
    label = entity.name if entity is not None else entity_id
    raw_alias = entity.display_alias if entity is not None else ""
    alias = _normalize_alias(raw_alias) if raw_alias else _alias_for(item_type, entity_id)
    return _ResolvedItem(
        local_id=entity_id,
        item_type=item_type,
        alias=alias,
        label=label,
        description=_short_description(entity),
        technology=technology,
        external=external,
        shape=None,  # model-backed items use technology inference
        is_store=_is_store(entity),
    )


def _declared_technology(entity: EntityRecord | None, attributes: Sequence[str], limit: int) -> str:
    """The technology line a C4 box shows, read from the attributes the diagram type names.

    C4's element macros take a short technology as their third argument — "Python, FastAPI" — and it
    is what distinguishes one container from another at that level. The model already records it,
    in attributes the *profile* names; a model-backed view rendered an empty string and threw all of
    it away.

    Which attributes supply it is declared in the diagram type's own `config.yaml`, because these
    names belong to a specialization catalogue and not to C4. Entries are taken in the declared
    order and capped, which is what keeps the result to the one short phrase the notation has room
    for: languages first, then the framework the author listed first.

    A version specifier is dropped — a box saying "FastAPI" is read at a glance and one saying
    "FastAPI >=0.115.0" is not, and the version is a fact about the dependency rather than about
    what the container is.
    """
    if not attributes or limit <= 0:
        return ""
    if entity is None:
        return ""
    declared = entity.attributes
    entries: list[str] = []
    for name in attributes:
        for entry in _attribute_entries(declared.get(name)):
            stripped = _VERSION_SPEC_RE.sub("", entry).strip()
            if stripped and stripped not in entries:
                entries.append(stripped)
            if len(entries) >= limit:
                return ", ".join(entries)
    return ", ".join(entries)


def _attribute_entries(raw: object) -> list[str]:
    """One attribute's values, whether it was written as a list or as a JSON-encoded one.

    Attribute values reach the record as they were authored. A list-typed attribute round-trips
    through the frontmatter as a JSON string, so both shapes are live in the same repository.
    """
    if isinstance(raw, (list, tuple)):
        return [str(item) for item in raw]
    text = str(raw or "").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return [text]
        return [str(item) for item in parsed] if isinstance(parsed, list) else [text]
    return [text]


def _host_technology(item_type: str, artifact_type: str) -> str:
    """What kind of host a deployment node is, for its second label line.

    The model's own type is what is known about a projected host — a reader learns something from
    "System Software" and nothing from "node", which is the C4 item type they can already see.
    """
    if item_type != "node" or not artifact_type:
        return ""
    return artifact_type.replace("-", " ").title()


#: What a technology-layer element has to be for its name to serve as a container's technology line.
_TECHNOLOGY_PROVIDER_TYPES: frozenset[str] = frozenset({"system-software", "technology-node"})


def _served_technology(
    entity: EntityRecord | None, entity_id: str, query: ModelQuery, limit: int
) -> str:
    """A store's technology, read from the system software the model says serves it.

    A data store's technology is the engine that runs it — SQLite for the read model, Git and the
    file system for the repository — and that is a fact the model already holds as a technology
    element *serving* the store. Nothing had to be authored twice for it; it simply was not being
    read, so both stores reached the renderer with an empty technology and drew as plain boxes.

    Only for a store, and that restriction is the rule rather than a caution. What serves an
    ordinary application is its *host*, which is the deployment view's subject and not its technology
    line: a repository whose components carry no technology attributes would otherwise have every
    box labelled with the machine or runtime it happens to sit on, and C4-PlantUML infers the shape
    from that string — so a component served by something named for a database would be drawn as a
    cylinder. A store is the one case where the serving technology *is* what the box is made of.
    """
    if limit <= 0 or not _is_store(entity):
        return ""
    names: list[str] = []
    for conn in query.find_connections_for(entity_id, direction="inbound"):
        if conn.conn_type != "archimate-serving":
            continue
        provider = query.get_entity(conn.source)
        if provider is None or provider.artifact_type not in _TECHNOLOGY_PROVIDER_TYPES:
            continue
        if provider.name not in names:
            names.append(provider.name)
        if len(names) >= limit:
            break
    return ", ".join(names)


def _nest(
    internal_items: list[_ResolvedItem], contained_by: dict[str, str]
) -> list[_ResolvedItem]:
    """Move each item the projection placed inside another into that one's ``children``.

    Empty ``contained_by`` leaves the list exactly as it was, which is every level but deployment.

    Built bottom-up, and that is the whole of the difficulty. The first version attached each child
    to its parent's *pre-`replace`* object, so a chain of three — a host holding a container holding
    an application — kept the container and silently dropped what was inside it. `contained_by` can
    express any chain, so a structure the renderer could not draw was reachable without anything
    failing; a diagram simply came back missing its contents.

    A cycle in the declared containment would recurse forever, so each branch carries the ancestors
    it has already passed through and stops rather than following one.
    """
    if not contained_by:
        return internal_items
    by_id = {item.local_id: item for item in internal_items}
    children_of: dict[str, list[str]] = {}
    for child_id, parent_id in contained_by.items():
        if child_id != parent_id and child_id in by_id and parent_id in by_id:
            children_of.setdefault(parent_id, []).append(child_id)
    nested_ids = {child_id for group in children_of.values() for child_id in group}

    def build(item_id: str, ancestors: frozenset[str]) -> _ResolvedItem:
        seen = ancestors | {item_id}
        kids = tuple(
            build(child_id, seen)
            for child_id in children_of.get(item_id, ())
            if child_id not in seen
        )
        return replace(by_id[item_id], children=kids)

    return [
        build(item.local_id, frozenset())
        for item in internal_items
        if item.local_id not in nested_ids
    ]


def _boundary_aliases(
    scope_items: Sequence[_ResolvedItem],
    nested_internal: Sequence[_ResolvedItem],
    scope_render_mode: str,
) -> set[str]:
    """Every alias that names a boundary rather than an element, so no edge may land on one.

    A C4 boundary is not an element and cannot be an endpoint of a relationship. Three things are
    drawn as one and they were not recognised as the same thing: the scope in `boundary` mode, a
    grouping, and a deployment node holding containers. Naming only the first left four arrows
    running from the Architecture Backend's own boundary to components inside it — which reads as a
    thing depending on its own parts — and then, once groupings became boundaries too, six more
    running onto the Assurance Module group.

    "Has children" is the test rather than the item type, because it is exactly the test the
    renderer applies when it decides to open a boundary instead of drawing a box: a grouping the
    level draws nothing inside is not drawn at all, and an unoccupied deployment node is a plain
    container that an edge may perfectly well reach.

    The membership is still recorded — `scope_of` says which boundary contains the element — and it
    is only the drawing that is declined. Context and landscape draw their scope as an element, so
    there the same edge is meaningful and is kept.
    """
    scope_boundary = {i.alias for i in scope_items} if scope_render_mode == "boundary" else set()
    return scope_boundary | {i.alias for i in nested_internal if i.children}


def _flatten(items: Iterable[_ResolvedItem]) -> list[_ResolvedItem]:
    """Every item in a nesting, at any depth — what "drawn" means once boxes can hold boxes."""
    out: list[_ResolvedItem] = []
    for item in items:
        out.append(item)
        out.extend(_flatten(item.children))
    return out


def resolve_model_backed(
    diagram_type: str,
    repo_root: Path,
    diagram_entities: Mapping[str, object],
    scope_entity_ids: tuple[str, ...],
    scope_entity_type: str,
    scope_render_mode: str,
    internal_c4_type: str,
    person_archimate_types: frozenset[str],
    technology_attributes: Sequence[str] = (),
    technology_limit: int = 0,
) -> _ResolvedState:
    from src.diagram_types.c4._projection import project_c4_scope  # noqa: PLC0415
    from src.infrastructure.artifact_index import shared_artifact_index  # noqa: PLC0415

    query = shared_artifact_index([repo_root])
    scope_entities = []
    for scope_entity_id in scope_entity_ids:
        scope_entity = query.get_entity(scope_entity_id)
        if scope_entity is None:
            raise DiagramSelectionError(f"{diagram_type!r}: scope entity {scope_entity_id!r} not found")
        scope_entities.append(scope_entity)

    projection = project_c4_scope(
        diagram_type, scope_entity_ids, query,
        internal_c4_type=internal_c4_type,
        scope_entity_type=scope_entity_type,
        person_archimate_types=person_archimate_types,
    )

    raw_included = diagram_entities.get(INCLUDED_IDS_KEY)
    raw_excluded = diagram_entities.get(EXCLUDED_IDS_KEY)
    included_only: set[str] | None = None
    excluded_ids: set[str] = set()
    if isinstance(raw_included, list) and raw_included:
        included_only = {str(x) for x in raw_included}
    elif isinstance(raw_excluded, list) and raw_excluded:
        excluded_ids = {str(x) for x in raw_excluded}

    scope_items = tuple(
        _item_from_entity(entity, entity_id, scope_entity_type, external=False)
        for entity, entity_id in zip(scope_entities, scope_entity_ids, strict=True)
    )
    scope_id_set = set(scope_entity_ids)
    internal_items: list[_ResolvedItem] = []
    outside_items: list[_ResolvedItem] = []

    for proj_item in projection.items:
        if proj_item.role == "scope":
            continue
        eid = proj_item.entity_id
        if included_only is not None and eid not in included_only:
            continue
        if eid in excluded_ids:
            continue
        entity = query.get_entity(eid)
        if entity is None:
            continue
        resolved = _item_from_entity(
            entity, eid, proj_item.item_type,
            external=is_externally_styled(proj_item.role, proj_item.item_type),
            technology=(
                _host_technology(proj_item.item_type, proj_item.artifact_type)
                or _declared_technology(entity, technology_attributes, technology_limit)
                or _served_technology(entity, eid, query, technology_limit)
            ),
        )
        if proj_item.role == "internal":
            internal_items.append(resolved)
        else:
            outside_items.append(resolved)

    # Additive validated inclusion — extra IDs in `_included_entity_ids` that the projection did not
    # yield.
    #
    # Two kinds, and treating them alike was a defect. An id the model places *inside* the scope is
    # not a neighbour: the type table left it undrawn, and naming it explicitly is the author
    # overriding that default, so it is drawn inside with the level's own item type. Calling it a
    # `software-system` instead put the backend's own REST interface outside its boundary in the
    # notation reserved for third-party software. `scope_of` is what the projection already knows
    # about descendants it does not draw, so the question is asked of it rather than walked again.
    if included_only:
        projected_eids = scope_id_set | {i.local_id for i in internal_items} | {i.local_id for i in outside_items}
        inside_scope = dict(projection.scope_of)
        for extra_eid in sorted(included_only - projected_eids):
            entity = query.get_entity(extra_eid)
            if entity is None:
                continue
            if extra_eid in inside_scope:
                internal_items.append(
                    _item_from_entity(entity, extra_eid, internal_c4_type, external=False)
                )
            elif any(
                c.source in projected_eids or c.target in projected_eids
                for c in query.find_connections_for(extra_eid, direction="any")
            ):
                outside_items.append(_item_from_entity(entity, extra_eid, "software-system", external=True))

    internal_items = _nest(internal_items, dict(projection.contained_by))

    # Everything inside the scope, at whatever depth the nesting put it. Reading the *top* level
    # instead was correct for as long as only a deployment view nested anything; once a grouping
    # became a boundary at the zoom levels, almost every internal item moved inside one and the
    # set below silently emptied — taking the association-direction rule that consults it with it.
    nested_internal = _flatten(internal_items)
    drawn = [*scope_items, *nested_internal, *outside_items]
    all_displayed = scope_id_set | {i.local_id for i in drawn}
    alias_by_eid = {i.local_id: i.alias for i in drawn}

    model_conns: list[ConnectionRecord] = []
    for cid in projection.connection_ids:
        conn = query.get_connection(cid)
        if conn is None:
            continue
        if conn.source not in all_displayed and conn.target not in all_displayed:
            continue
        model_conns.append(conn)
    model_conns.sort(key=lambda x: x.artifact_id)

    # Build the C4 edge list with direction normalisation and deduplication.
    #
    # An endpoint the diagram does not draw is a structural descendant inside somebody's boundary,
    # and its edge belongs on that boundary. Which boundary comes from the projection's declared
    # `scope_of` rather than from the diagram type — the rule used to read "if this is the context
    # level, everything falls back to the one root", which a landscape's several roots cannot say.
    rollup_alias = {
        entity_id: alias
        for entity_id, root in projection.scope_of
        if (alias := alias_by_eid.get(root))
    }
    provider_aliases = {i.alias for i in scope_items} | {i.alias for i in nested_internal}
    seen_pairs: set[tuple[str, str]] = set()
    conn_list: list[_C4Connection] = []
    boundary_aliases = _boundary_aliases(scope_items, nested_internal, scope_render_mode)
    for c in model_conns:
        src = alias_by_eid.get(c.source) or rollup_alias.get(c.source)
        tgt = alias_by_eid.get(c.target) or rollup_alias.get(c.target)
        if src is None or tgt is None:
            continue
        if src in boundary_aliases or tgt in boundary_aliases:
            continue
        if c.conn_type == "archimate-serving":
            src, tgt = tgt, src
        elif c.conn_type == "archimate-association" and src in provider_aliases and tgt not in provider_aliases:
            src, tgt = tgt, src
        if src == tgt:
            continue
        pair = (src, tgt)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        conn_list.append(_C4Connection(
            src_alias=src, tgt_alias=tgt,
            label=_conn_label(c),
            artifact_id=c.artifact_id,
        ))

    return _ResolvedState(
        scope_items=scope_items,
        scope_render_mode=scope_render_mode,
        internal_items=internal_items,
        outside_items=outside_items,
        connections=tuple(conn_list),
        entity_ids=tuple(sorted(all_displayed)),
        connection_artifact_ids=tuple(c.artifact_id for c in model_conns),
    )

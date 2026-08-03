"""type_guidance.py — Focused modeling guidelines for entity types and diagram types.

Returns create_when / never_create_when guidance plus permitted relationships for a
selectable subset of ArchiMate domains or entity types; or when_to_use / when_not_to_use,
diagram_entities_schema, own_entity_types, and optional puml_notes guidance for a
specific diagram type.

Progressive discovery:
  - Pass diagram_type to get authoring guidance for one diagram type.
  - Pass filter to get detailed guidance for specific entity types or domains.
  - Pass both to get diagram type guidance alongside filtered entity type guidance.
  - Pass neither to get guidance for all entity types (large; prefer filtering).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from src.application.guidance_composition import GuidanceContextView
from src.application.modeling.diagram_kind_palette import (
    diagram_kind_connection_types,
    diagram_kind_entity_types,
)
from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.diagrams.allowed_bindings import serialize_allowed_bindings
from src.domain.modules.module_types import ConnectionTypeName, EntityTypeName
from src.domain.ontology_representation.ontology_protocol import DiagramTypeWriteGuidance
from src.domain.ontology_representation.specializations import SpecializationCatalog
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.write.artifact_write._connection_metadata_guidance import (
    connection_type_guidance,
    serialize_specialization,
)


def pair_connection_guidance(source_type: str, target_type: str) -> dict[str, object]:
    """Return directional pair-legality for (source_type, target_type).

    Derives direction cleanly from ``classify_connections(source_type)`` so that
    outgoing/incoming/symmetric are unambiguous.  Returns a dict with keys:
    ``source``, ``target``, ``outgoing``, ``incoming``, ``symmetric``.
    ``error`` is set when either type is unknown.
    """
    all_types = _registry().all_entity_types()
    unknown = [t for t in (source_type, target_type) if t not in all_types]
    if unknown:
        return {
            "error": f"Unknown entity type(s): {unknown!r}. Provide concrete type names.",
            # Which input was wrong, named here because this is the code that knows. The REST adapter
            # turns these rejections into a typed 422; MCP returns the mapping as-is, and an extra key
            # costs it nothing. Matching on the message would be the alternative, and prose is not a
            # contract.
            "field": "entity_type",
            "known_types": sorted(all_types.keys()),
        }
    c = _classify_connections(source_type)
    return {
        "source": source_type,
        "target": target_type,
        "outgoing": sorted(c["outgoing"].get(target_type, [])),
        "incoming": sorted(c["incoming"].get(target_type, [])),
        "symmetric": sorted(c["symmetric"].get(target_type, [])),
    }


@lru_cache(maxsize=1)
def _registry():
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415

    return get_module_registry()


def _classify_connections(source_type: str) -> dict[str, dict[str, list[str]]]:
    """Classify permissible connections into outgoing/incoming/symmetric."""
    prs = _registry().aggregated_permitted_relationships()
    src = EntityTypeName(source_type)
    outgoing: dict[str, list[str]] = {}
    incoming: dict[str, list[str]] = {}
    symmetric: dict[str, list[str]] = {}

    for tgt, ct in prs.by_source().get(src, []):
        ct_info = _registry().find_connection_type(ConnectionTypeName(str(ct)))
        if ct_info is not None and ct_info.symmetric:
            symmetric.setdefault(str(tgt), []).append(str(ct))
        else:
            outgoing.setdefault(str(tgt), []).append(str(ct))

    for src2, ct in prs.by_target().get(src, []):
        ct_info = _registry().find_connection_type(ConnectionTypeName(str(ct)))
        if ct_info is not None and ct_info.symmetric:
            if str(src2) not in symmetric:
                symmetric.setdefault(str(src2), []).append(str(ct))
        else:
            incoming.setdefault(str(src2), []).append(str(ct))

    return {"outgoing": outgoing, "incoming": incoming, "symmetric": symmetric}


def get_type_guidance(
    filter: list[str] | None = None,  # noqa: A002
    diagram_type: str | None = None,
    target: str | None = None,
    catalogs: RuntimeCatalogs | None = None,
    repo_root: Path | None = None,
) -> dict[str, object]:
    """Return focused modeling guidelines for the requested entity types, domains, or diagram type.

    ``filter`` accepts entity-type names (e.g. ``["requirement", "goal"]``) or domain names
    (e.g. ``["motivation", "strategy"]``).  Resolved unambiguously: if every item matches a
    known entity-type name it is an entity-type filter; otherwise a domain filter.

    ``diagram_type`` selects one diagram type (e.g. ``"archimate-motivation"`` or ``"activity"``).
    When provided, the response includes a ``diagram_type_guidance`` block with when_to_use,
    when_not_to_use, accepted_domains, own entity type guidance, and puml_notes.

    ``target`` enables pair-legality guidance: when set, ``filter`` must contain exactly one
    concrete entity-type name (the source).  The response gains a ``pair_guidance`` block with
    outgoing/incoming/symmetric connection types for the (source, target) pair.  A domain
    filter, multiple source types, or ``target`` without ``filter`` is a validation error.

    Passing both ``diagram_type`` and ``filter`` returns the diagram type block plus entity type
    guidance for the filtered subset.  Omit both to return guidance for all entity types.

    ``catalogs`` supplies the specialization catalog used to enumerate per-type specializations
    (entity ``entity_types[].specializations`` and connection ``connection_types``); callers with
    an injected ``RuntimeCatalogs`` (REST) pass it, callers without one (MCP) omit it and a
    process-wide default is built lazily.

    ``repo_root`` is what makes schemas resolvable — they are per-repo files. With it, each
    connection type and each of its specializations also carries the effective merged
    metadata schema it authors against (and whether the pair is quarantined). Without it the
    payload is guidance only, exactly as before.
    """
    cats = catalogs if catalogs is not None else process_runtime_catalogs()
    result: dict[str, object] = {}

    if target is not None:
        if filter is None:
            return {
                "error": "target requires filter to contain exactly one concrete entity type name.",
                "field": "filter",
            }
        all_types = _registry().all_entity_types()
        concrete = [t for t in filter if t in all_types]
        if len(concrete) != 1 or len(filter) != 1:
            return {
                "error": (
                    "target requires filter with exactly one concrete entity type (e.g. ['requirement']). "
                    "Domain filters and multiple types are not allowed."
                ),
                "field": "filter",
                "filter_received": filter,
            }
        result["pair_guidance"] = pair_connection_guidance(concrete[0], target)

    if diagram_type is not None:
        diagram_type_mod = _registry().find_diagram_type(diagram_type)
        if diagram_type_mod is None:
            known = sorted(_registry().all_diagram_types().keys())
            return {
                "error": f"Unknown diagram_type {diagram_type!r}.",
                "field": "diagram_type",
                "known_diagram_types": known,
            }
        result["diagram_type_guidance"] = _serialize_diagram_type_guidance(
            diagram_type, diagram_type_mod.write_guidance(), cats
        )

    if filter is not None or diagram_type is None:
        entity_section = _entity_type_guidance(filter, cats.specializations, cats.guidance_context)
        result.update(entity_section)
        result["connection_types"] = connection_type_guidance(
            cats.specializations,
            profile_registry=cats.profiles,
            repo_root=repo_root,
            connection_types={str(name): info for name, info in _registry().all_connection_types().items()},
        )

    return result


GUIDANCE_EMPTY_HINT = (
    "No create_when/never_create_when creation guidance has been imported for these entity "
    "types yet — the shipped ontology ships with this text stripped for license reasons. "
    "Run `arch-import-guidance` to import the published guidance file, then restart the "
    "backend. See docs/05-extensibility/schemata-and-profiles.md."
)


def _entity_type_guidance_is_empty(entries: list[dict[str, object]]) -> bool:
    return bool(entries) and all(not e.get("create_when") and not e.get("never_create_when") for e in entries)


def _serialize_diagram_type_guidance(
    name: str,
    g: DiagramTypeWriteGuidance,
    catalogs: RuntimeCatalogs,
) -> dict[str, object]:
    """Guidance for one diagram type, including the types it will actually accept.

    ``accepted_entity_types`` / ``accepted_connection_types`` are the **palette** — the same lists
    `GET /api/diagram-types/{t}/entity-types` and its connection twin serve, read from the one
    composition in `application.modeling.diagram_kind_palette` so the two transports cannot disagree.

    They are here rather than behind a new tool or a new parameter, and that placement is the point.
    `artifact_authoring_guidance` already takes `diagram_type` and is already the tool an agent asks
    "what may I author on this diagram" — it just answered with accepted *domains* and left the agent to
    derive the type list from them. That derivation is what these two REST routes do centrally, and the
    agent could not reproduce the viewpoint-narrowed form of it at all. Enriching a payload costs no
    tool surface and no argument; a `diagram_palette` tool would have been a second address for a
    question this tool is already asked.

    Unnarrowed on purpose: narrowing takes a viewpoint, which is the one thing this signature does not
    have. REST offers it as `?viewpoint=`, and adding it here later is a parameter on the tool whose job
    it is rather than on a bystander — worth doing when an agent flow needs it, not before.
    """
    out: dict[str, object] = {
        "name": name,
        "when_to_use": g.when_to_use,
        "when_not_to_use": g.when_not_to_use,
        "accepted_entity_types": diagram_kind_entity_types(name, catalogs),
        "accepted_connection_types": diagram_kind_connection_types(name, catalogs),
    }
    if g.accepted_domains:
        out["accepted_domains"] = list(g.accepted_domains)
    if g.diagram_entities_schema is not None:
        out["diagram_entities_schema"] = g.diagram_entities_schema
    if g.own_entity_types:
        own_entries = [_serialize_own_entity_type(oe) for oe in g.own_entity_types]
        out["own_entity_types"] = own_entries
        if _entity_type_guidance_is_empty(own_entries):
            out["guidance_status"] = "empty"
            out["guidance_hint"] = GUIDANCE_EMPTY_HINT
    if g.puml_notes:
        out["puml_notes"] = list(g.puml_notes)
    if g.allowed_bindings is not None:
        out["allowed_bindings"] = serialize_allowed_bindings(g.allowed_bindings)
    return out


def _serialize_own_entity_type(oe) -> dict[str, object]:  # type: ignore[no-untyped-def]
    entry: dict[str, object] = {
        "entity_type": oe.entity_type,
        "label": oe.label,
        "min": oe.min,
        "max": oe.max,
        "classes": list(oe.classes),
        "create_when": oe.create_when,
        "never_create_when": oe.never_create_when,
    }
    if oe.permitted_mappings.has_any():
        entry["permitted_mappings"] = oe.permitted_mappings.as_config()
    managed: dict[str, str] = {"id": "required"}
    if oe.managed_fields is not None:
        managed.update(dict(oe.managed_fields))
    elif oe.permitted_mappings.has_any():
        managed["label"] = "optional — falls back to linked model entity name"
        managed["entity_id"] = "required" if oe.mapping_required else "optional — links to a model entity"
    else:
        managed["label"] = "required"
    entry["managed_fields"] = managed
    if oe.properties:
        entry["domain_properties"] = {p.name: {"required": p.required, **p.schema} for p in oe.properties}
    return entry


def _entity_type_guidance(
    filter: list[str] | None,  # noqa: A002
    specialization_catalog: SpecializationCatalog,
    guidance_context: GuidanceContextView,
) -> dict[str, object]:
    # Internal entity types (e.g. global-artifact-reference) are never manually created — they
    # are produced exclusively by mechanisms like artifact promotion. Excluding them here keeps
    # every guidance consumer (REST wizard, MCP agents) from offering uncreatable types; the
    # create path independently rejects them (`entity.py::is_internal_entity_type` guard).
    all_infos = {
        name: info for name, info in _registry().all_entity_types().items() if not info.internal
    }

    if filter is None:
        selected = list(all_infos.values())
        include_domain = True
        domain_context: list[str] | None = None
    else:
        entity_type_hits = [n for n in filter if n in all_infos]
        if len(entity_type_hits) == len(filter):
            selected = [all_infos[EntityTypeName(n)] for n in filter]
            include_domain = True
            domain_context = None
        else:
            unknown_types = [n for n in filter if n not in all_infos]
            domain_set = {d.lower() for d in filter}
            selected = [
                info for info in all_infos.values() if info.hierarchy and info.hierarchy[0].lower() in domain_set
            ]
            if not selected:
                return {
                    "error": (
                        f"No matches found for filter {filter!r}. "
                        "Provide known entity-type names (e.g. 'requirement') "
                        "or domain names (e.g. 'motivation')."
                    ),
                    "unknown": unknown_types,
                }
            include_domain = False
            domain_context = filter

    selected = sorted(
        selected,
        key=lambda x: (x.hierarchy[0] if x.hierarchy else "", x.artifact_type),
    )

    entries: list[dict[str, object]] = []
    for info in selected:
        connections = _classify_connections(info.artifact_type)
        entry: dict[str, object] = {
            "name": info.artifact_type,
            "prefix": info.prefix,
        }
        if include_domain:
            entry["domain"] = info.hierarchy[0] if info.hierarchy else ""
        entry["classes"] = list(info.classes)
        entry["create_when"] = info.create_when
        entry["never_create_when"] = info.never_create_when
        entry["permitted_connections"] = connections
        entry["specializations"] = [
            serialize_specialization(s) for s in specialization_catalog.for_type("entity", info.artifact_type)
        ]
        context = guidance_context.context_for(info.artifact_type)
        if context:
            entry["context"] = [{"level": c.level_id, "node": c.node_id, "text": c.text} for c in context]
        entries.append(entry)

    out: dict[str, object] = {"entity_types": entries, "total": len(entries)}
    if domain_context:
        out["domains"] = domain_context
    if _entity_type_guidance_is_empty(entries):
        out["guidance_status"] = "empty"
        out["guidance_hint"] = GUIDANCE_EMPTY_HINT
    return out

"""Derive a module's guidance hierarchy from the metadata it already declares.

Shipped OntologyModules (archimate-4, assurance) do not hand-author a guidance tree — their
tree is the standard ``domain → entity type → specialization`` shape read straight from their
entity-type metadata (each ``EntityTypeInfo.hierarchy[0]`` is that type's domain). A module
that needs a different tree may expose a ``guidance_hierarchy()`` method;
:func:`resolve_guidance_hierarchy` prefers it and otherwise derives the standard tree, so
extending to a new shape never means editing shipped modules.

Specialization node ids are qualified as ``"<type>::<slug>"`` because a specialization slug is
unique only per parent type (two types may each declare a ``core`` specialization); the
qualification keeps node identity unique within the specialization level while its
``parent_node_id`` still points at the bare type name one level up.
"""

from __future__ import annotations

from src.domain.guidance.guidance_hierarchy import GuidanceHierarchy, GuidanceLevel, GuidanceNode
from src.domain.ontology_representation.ontology_protocol import OntologyModule

META_ONTOLOGY_LEVEL = "meta_ontology"
DOMAIN_LEVEL = "domain"
ENTITY_TYPE_LEVEL = "entity_type"
SPECIALIZATION_LEVEL = "specialization"

_STANDARD_LEVELS = (
    GuidanceLevel(META_ONTOLOGY_LEVEL, "Meta-ontology", 0),
    GuidanceLevel(DOMAIN_LEVEL, "Domain", 1),
    GuidanceLevel(ENTITY_TYPE_LEVEL, "Entity type", 2),
    GuidanceLevel(SPECIALIZATION_LEVEL, "Specialization", 3),
)


def specialization_node_id(type_name: str, slug: str) -> str:
    """The qualified specialization-level node id for ``slug`` under ``type_name``."""
    return f"{type_name}::{slug}"


def derive_standard_hierarchy(module: OntologyModule, *, alias: str) -> GuidanceHierarchy:
    """Build the meta-ontology→domain→entity-type→specialization tree from ``module``'s declared
    metadata. ``alias`` is the module's guidance alias — the single ``meta_ontology``-level root
    node's id (kept traceable to the overlay's alias field) and the parent of every domain node.
    """
    domains: set[str] = set()
    leaf_nodes: list[GuidanceNode] = []
    for type_name, info in module.entity_types.items():
        domain = info.hierarchy[0] if info.hierarchy else ""
        domains.add(domain)
        leaf_nodes.append(GuidanceNode(ENTITY_TYPE_LEVEL, str(type_name), parent_node_id=domain))
        for spec in module.specialization_catalog.for_type("entity", str(type_name)):
            leaf_nodes.append(
                GuidanceNode(
                    SPECIALIZATION_LEVEL,
                    specialization_node_id(str(type_name), spec.slug),
                    parent_node_id=str(type_name),
                )
            )
    meta_node = GuidanceNode(META_ONTOLOGY_LEVEL, alias)
    domain_nodes = [GuidanceNode(DOMAIN_LEVEL, domain, parent_node_id=alias) for domain in sorted(domains)]
    return GuidanceHierarchy(levels=_STANDARD_LEVELS, nodes=(meta_node, *domain_nodes, *leaf_nodes))


def resolve_guidance_hierarchy(module: OntologyModule, *, alias: str) -> GuidanceHierarchy:
    """A module's own ``guidance_hierarchy()`` if it declares one, else the standard derivation."""
    provided = getattr(module, "guidance_hierarchy", None)
    if callable(provided):
        result = provided()
        if isinstance(result, GuidanceHierarchy):
            return result
    return derive_standard_hierarchy(module, alias=alias)

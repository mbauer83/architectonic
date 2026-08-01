"""Which derivation domain an entity type belongs to.

The one question both halves of the derivation rules need: the restrictions declare which domains a
derived relationship may cross, and the derivation itself asks each endpoint which domain it is in.

Both had a copy — of the vocabulary *and* of the classification, byte-identically — because
``relationship_derivation`` already imports ``relationship_derivation_restrictions``, so the second
copy was the only way to ask the question from the lower module. A third module below both is what
that cycle was asking for.

**A known boundary debt, named rather than hidden.** The layer names below are ArchiMate's, sitting
in the generic relationship core. ``test_core_names_no_module_vocabulary`` records this class of leak
and deliberately does not cover it: the ontology should declare which derivation domain each of its
layers is, and this function should ask. Consolidating the two copies does not fix that — it makes it
one thing to fix instead of two that can disagree.
"""

from __future__ import annotations

from typing import Literal, cast

from src.domain.ontology_representation.ontology_types import EntityTypeInfo

DerivationDomain = Literal["motivation", "strategy", "core", "implementation_migration", "relationships"]

#: The layers that derive as one domain: a relationship crossing between them is not crossing a
#: derivation boundary.
_CORE_LAYERS = frozenset({"business", "application", "technology", "common"})


def derivation_domain(info: EntityTypeInfo) -> DerivationDomain:
    """The derivation domain ``info`` belongs to, from its class and its hierarchy.

    A junction is in ``relationships`` whatever its hierarchy says: it stands for a relationship
    rather than for anything a layer contains.
    """
    if "junction" in info.classes:
        return "relationships"
    if not info.hierarchy:
        raise ValueError(f"entity type {info.artifact_type!r} has no hierarchy")
    head = info.hierarchy[0]
    if head in _CORE_LAYERS:
        return "core"
    if head == "implementation":
        return "implementation_migration"
    if head in {"motivation", "strategy"}:
        return cast(DerivationDomain, head)
    raise ValueError(f"entity type {info.artifact_type!r} has unknown derivation domain {head!r}")

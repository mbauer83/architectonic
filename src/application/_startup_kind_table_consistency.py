"""The kind table against itself and against every other declaration of an id prefix.

An id's prefix is read to tell what the id names: `ICO@…` is an icon, `SCR@…` a scratchpad, and no
type is consulted for either. That reading is only true while nothing else mints the same prefix, and
three other things mint prefixes — an entity type, a diagram type, and a document type, whose
abbreviation is repository data any deployment may write. Nothing compared them: a document type
abbreviated `ICO` would have filed its documents under ids the icon reference reads as icons.

So a kind's own prefix is resolved against one map of *prefix → who else declares it*:

* the product's catalogues, in `validate_registry_consistency`, wherever a module registry is built;
* a repository's document types, in `validate_repo_compatibility`, when the repository is loaded.

**What is not checked here, and why.** That prefixes are unique among the *types* themselves. They
are not, by design that predates the table: a diagram type's prefix is derived from its name, and
`matrix` and `activity` derive the `MAT` and `ACT` that the `material` and `business-actor` entity
types declare. A type's prefix is read together with the kind the file's place gives it; a kind's own
prefix is read alone, which is why it is the one that must be claimed by nothing else.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING

from src.application.modeling.artifact_write import prefix_for_diagram_type
from src.domain.repository.artifact_kind_consistency import kind_table_contradictions
from src.domain.repository.artifact_location import ARTIFACT_KINDS, KindDeclaration

if TYPE_CHECKING:
    from src.domain.modules.module_registry import ModuleRegistry


def kind_table_consistency_msgs(
    registry: "ModuleRegistry", kinds: tuple[KindDeclaration, ...] = ARTIFACT_KINDS
) -> Iterator[str]:
    """The table's own contradictions, then every kind prefix a product catalogue also declares."""
    yield from kind_table_contradictions(kinds)
    yield from kind_prefix_collisions(catalogue_prefix_owners(registry), kinds)


def catalogue_prefix_owners(registry: "ModuleRegistry") -> dict[str, list[str]]:
    """Every id prefix the product's type catalogues declare, with who declares it."""
    owners: dict[str, list[str]] = defaultdict(list)
    for type_name, info in registry.all_entity_types().items():
        if info.prefix:
            owners[info.prefix].append(f"the entity type {str(type_name)!r}")
    for diagram_type in registry.all_diagram_types().values():
        owners[prefix_for_diagram_type(str(diagram_type.name))].append(
            f"the diagram type {str(diagram_type.name)!r}, which derives it from its name"
        )
        for own in diagram_type.ui_config.diagram_only_types:
            if own.id_prefix:
                owners[own.id_prefix].append(
                    f"the entity type {own.entity_type!r} of the diagram type {str(diagram_type.name)!r}"
                )
    return dict(owners)


def document_type_prefix_owners(abbreviations: Mapping[str, str]) -> dict[str, list[str]]:
    """The same map for a repository's document types, from *doc type → the prefix its ids carry*."""
    owners: dict[str, list[str]] = defaultdict(list)
    for doc_type, prefix in sorted(abbreviations.items()):
        owners[prefix].append(f"the document type {doc_type!r}, as its `abbreviation`")
    return dict(owners)


def kind_prefix_collisions(
    owners: Mapping[str, list[str]], kinds: tuple[KindDeclaration, ...] = ARTIFACT_KINDS
) -> Iterator[str]:
    """A sentence for every kind whose own id prefix *owners* also declares."""
    for kind in kinds:
        if kind.id_prefix is None:
            continue
        for owner in owners.get(kind.id_prefix, ()):
            yield (
                f"Id prefix {kind.id_prefix!r} is the {kind.name} kind's own (the kind table, "
                f"`artifact_location`) and is also declared by {owner}. An id beginning "
                f"{kind.id_prefix}@ is read as a {kind.name} without asking its type, so "
                "that declaration must take another prefix."
            )

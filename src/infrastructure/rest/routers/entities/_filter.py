"""Shared entity structural filter (domain + type), used by the picker and reference search.

Both `/api/entity-display-search` and `/api/reference-search` need identical domain/entity-type
filtering semantics for their entity results — this module is the single predicate so the two
routers never drift.
"""

from __future__ import annotations

from collections.abc import Set as AbstractSet
from dataclasses import dataclass

from src.application.entity_type_predicates import is_internal_entity_type
from src.domain.modules.catalogs import OntologyCatalog
from src.domain.ontology_representation.artifact_types import EntityRecord


def parse_csv_filter(raw: str | None, *, lowercase: bool = False) -> frozenset[str]:
    values = (v.strip() for v in (raw or "").split(","))
    return frozenset((v.lower() if lowercase else v) for v in values if v)


@dataclass(frozen=True)
class EntityFilter:
    domains: frozenset[str]
    entity_types: frozenset[str]
    keywords: frozenset[str] = frozenset()
    """Exact keyword facet: an entity matches only if it carries every requested keyword
    (e.g. the wizard's `wizard-draft` session tag)."""

    @classmethod
    def from_params(
        cls,
        *,
        domains: str | None,
        entity_types: str | None,
        keywords: str | None = None,
    ) -> EntityFilter:
        return cls(
            domains=parse_csv_filter(domains, lowercase=True),
            entity_types=parse_csv_filter(entity_types),
            keywords=parse_csv_filter(keywords),
        )

    def matches(
        self,
        entity: EntityRecord,
        *,
        ontology: OntologyCatalog,
        accepted_entity_types: AbstractSet[str] | None = None,
    ) -> bool:
        if is_internal_entity_type(entity.artifact_type, ontology):
            return False
        if self.domains and entity.domain not in self.domains:
            return False
        if self.entity_types and entity.artifact_type not in self.entity_types:
            return False
        if self.keywords and not self.keywords.issubset(entity.keywords):
            return False
        return accepted_entity_types is None or entity.artifact_type in accepted_entity_types

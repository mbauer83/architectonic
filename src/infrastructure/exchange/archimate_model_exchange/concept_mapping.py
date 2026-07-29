"""Loads ``exchange_mapping.yaml`` and implements ``ExchangeConceptMapper`` (D10, parent
plan §4.5, WU-F3a/F3b): the Appendix E.4 migration table, both directions.

``ApplicationComponent`` specializations (``service``/``module``/``endpoint``) and
``Assignment`` specializations (``responsibility-assignment``/``behavior-assignment``) have
no dedicated table row — C19C has no native concrete type for them, so the row's own
default specialization is always ``None`` and the specialization can only come from the
document's ``archrepo-specialization`` extension property (import's ``specialization_hint``
/ export's ``extension_specialization``).

The export (reverse) direction is derived from the same table at construction time, not
hand-authored: rows carrying a ``warning`` (lossy import-only fallbacks, e.g.
``BusinessInteraction`` -> ``business-process``) are excluded whenever a non-lossy row
already covers the same ``(type, specialization)`` pair, so export always prefers the
canonical 3.x type over an import-only synonym.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml

from src.application.exchange.concept_mapping import (
    ElementMapping,
    ExportElementMapping,
    ExportRelationshipMapping,
    RelationshipMapping,
    UnmappableArchimateTypeError,
    UnmappableConceptError,
)

_MAPPING_PATH = Path(__file__).parent / "exchange_mapping.yaml"
_LAYER_NEUTRAL_TYPES = frozenset({"role", "collaboration", "service", "process", "function", "event"})
_DOMAINS = frozenset({"business", "application", "technology"})

_ReverseMap = dict[tuple[str, "str | None"], str]


def _load() -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    data = yaml.safe_load(_MAPPING_PATH.read_text(encoding="utf-8"))
    return data["elements"], data["relationships"]


def _build_reverse(table: dict[str, dict[str, str]]) -> _ReverseMap:
    reverse: _ReverseMap = {}
    # Pass 1: non-lossy rows only, so a canonical type always wins a same-key collision.
    for concept_type, row in table.items():
        if row.get("warning"):
            continue
        reverse.setdefault((row["type"], row.get("specialization")), concept_type)
    # Pass 2: lossy rows fill any remaining gap (e.g. ImplementationEvent is the only
    # carrier for bare "event" with no specialization) rather than going unrepresented.
    for concept_type, row in table.items():
        reverse.setdefault((row["type"], row.get("specialization")), concept_type)
    return reverse


class DeclarativeConceptMapper:
    """Reads the mapping table once at construction; stateless afterward."""

    def __init__(self, mapping_path: Path | None = None) -> None:
        if mapping_path is None:
            self._elements, self._relationships = _load()
        else:
            data = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
            self._elements, self._relationships = data["elements"], data["relationships"]
        self._elements_reverse = _build_reverse(self._elements)
        self._relationships_reverse = _build_reverse(self._relationships)

    def _lookup(
        self, table: dict[str, dict[str, str]], concept_type: str, kind: Literal["element", "relationship"]
    ) -> dict[str, str]:
        row = table.get(concept_type)
        if row is None:
            raise UnmappableConceptError(concept_type, kind)
        return row

    def element_to_archimate(self, concept_type: str, *, specialization_hint: str | None = None) -> ElementMapping:
        row = self._lookup(self._elements, concept_type, "element")
        return ElementMapping(
            archimate_type=row["type"],
            specialization=specialization_hint or row.get("specialization"),
            warning=row.get("warning"),
        )

    def relationship_to_archimate(
        self, concept_type: str, *, specialization_hint: str | None = None
    ) -> RelationshipMapping:
        row = self._lookup(self._relationships, concept_type, "relationship")
        return RelationshipMapping(
            connection_type=row["type"],
            specialization=specialization_hint or row.get("specialization"),
            warning=row.get("warning"),
        )

    def element_to_exchange(
        self, archimate_type: str, specialization: str | None = None, *, domain_hint: str | None = None
    ) -> ExportElementMapping:
        exact = self._elements_reverse.get((archimate_type, specialization))
        if exact is not None:
            return ExportElementMapping(concept_type=exact)

        if specialization is None:
            if archimate_type in _LAYER_NEUTRAL_TYPES and domain_hint in _DOMAINS:
                synthesized = f"{domain_hint}-{archimate_type}"
                via_domain = self._elements_reverse.get((archimate_type, synthesized))
                if via_domain is not None:
                    return ExportElementMapping(concept_type=via_domain)
        else:
            base = self._elements_reverse.get((archimate_type, None))
            if base is not None:
                return ExportElementMapping(concept_type=base, extension_specialization=specialization)

        # Last resort: a type with no native unspecialized/domain-matched form at all
        # (e.g. "role" has no generic C19C Role — only BusinessRole natively exists, so
        # application-role/technology-role carry as a compatible extension on it).
        candidates = sorted({v for (t, _s), v in self._elements_reverse.items() if t == archimate_type})
        if candidates:
            return ExportElementMapping(concept_type=candidates[0], extension_specialization=specialization)

        raise UnmappableArchimateTypeError(archimate_type, specialization, "element")

    def relationship_to_exchange(
        self, connection_type: str, specialization: str | None = None
    ) -> ExportRelationshipMapping:
        exact = self._relationships_reverse.get((connection_type, specialization))
        if exact is not None:
            return ExportRelationshipMapping(concept_type=exact)
        base = self._relationships_reverse.get((connection_type, None))
        if base is not None:
            return ExportRelationshipMapping(concept_type=base, extension_specialization=specialization)
        raise UnmappableArchimateTypeError(connection_type, specialization, "relationship")

"""C19C 3.x concrete-type <-> ArchiMate 4 type+specialization mapping (D10, parent plan
§4.5, WU-F3a/F3b): the application-defined port ``import_model.py``/``export_model.py``
depend on to resolve the Appendix E.4 migration table (both directions), implemented by the
declarative adapter in ``src/infrastructure/exchange/archimate_model_exchange/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


class UnmappableConceptError(Exception):
    """Raised (import direction) when a C19C concrete concept type has no ArchiMate 4
    mapping at all."""

    def __init__(self, concept_type: str, kind: Literal["element", "relationship"]) -> None:
        super().__init__(f"no ArchiMate 4 mapping for {kind} concept type {concept_type!r}")
        self.concept_type = concept_type
        self.kind = kind


class UnmappableArchimateTypeError(Exception):
    """Raised (export direction) when an ArchiMate 4 type/specialization has no C19C
    exchange representation at all — never expected in practice given full E.4 coverage,
    but the mapper must fail loudly rather than guess if this repo's ontology is ever
    extended with a type the table doesn't know about."""

    def __init__(
        self, archimate_type: str, specialization: str | None, kind: Literal["element", "relationship"]
    ) -> None:
        label = f"{archimate_type}+{specialization}" if specialization else archimate_type
        super().__init__(f"no C19C exchange mapping for ArchiMate 4 {kind} {label!r}")
        self.archimate_type = archimate_type
        self.specialization = specialization
        self.kind = kind


@dataclass(frozen=True)
class ElementMapping:
    archimate_type: str
    specialization: str | None = None
    warning: str | None = None


@dataclass(frozen=True)
class RelationshipMapping:
    connection_type: str
    specialization: str | None = None
    warning: str | None = None


@dataclass(frozen=True)
class ExportElementMapping:
    concept_type: str
    extension_specialization: str | None = None
    """Set when *concept_type* is a compatible-extension carrier, not a native C19C type
    for the requested specialization — the caller must emit it as an
    ``archrepo-specialization`` extension property."""


@dataclass(frozen=True)
class ExportRelationshipMapping:
    concept_type: str
    extension_specialization: str | None = None


class ExchangeConceptMapper(Protocol):
    """Both directions of the E.4 migration table.

    Import: ``specialization_hint`` is the ``archrepo-specialization`` extension property
    value, when the source document carries one (e.g. re-importing a document this system
    exported); it overrides the mapping's own default specialization, which lets
    generically-mapped concepts (``ApplicationComponent`` -> ``service``/``module``/
    ``endpoint``, ``Assignment`` -> ``responsibility-assignment``/``behavior-assignment``)
    round-trip losslessly.

    Export: ``domain_hint`` (an entity's ``hierarchy[0]`` — ``business``/``application``/
    ``technology``) resolves a layer-neutral type (``role``/``collaboration``/``service``/
    ``process``/``function``/``event``) with no recorded specialization to its default
    layer variant, per parent plan §4.5.
    """

    def element_to_archimate(
        self, concept_type: str, *, specialization_hint: str | None = None
    ) -> ElementMapping:
        """Raises ``UnmappableConceptError`` for an unrecognized concept type."""
        ...

    def relationship_to_archimate(
        self, concept_type: str, *, specialization_hint: str | None = None
    ) -> RelationshipMapping:
        """Raises ``UnmappableConceptError`` for an unrecognized concept type."""
        ...

    def element_to_exchange(
        self, archimate_type: str, specialization: str | None = None, *, domain_hint: str | None = None
    ) -> ExportElementMapping:
        """Raises ``UnmappableArchimateTypeError`` if no representation exists at all."""
        ...

    def relationship_to_exchange(
        self, connection_type: str, specialization: str | None = None
    ) -> ExportRelationshipMapping:
        """Raises ``UnmappableArchimateTypeError`` if no representation exists at all."""
        ...

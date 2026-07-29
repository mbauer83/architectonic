"""The C19C v3.1 model-exchange document shape (parent plan §4.5, WU-F2): a faithful,
ArchiMate-4-agnostic mirror of the ``archimate3_Model.xsd`` root ``model`` element —
concrete-type mapping (3.x <-> ArchiMate 4 + specialization) is WU-F3a/F3b's job, not this
codec's. Scope is deliberately the subset the reviewed mapping (``REVIEW-archimate-exchange-
readiness.md``) actually covers: elements, relationships, properties, property definitions.
``organizations``/``metadata`` (folder trees, model metadata) are out of scope — the review
document's Mapping Summary never references them, so the codec has nothing to preserve them
for yet; recorded as a scope decision, not an oversight.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LangString:
    """One ``LangStringType`` instance: text plus an optional ``xml:lang``. A property
    or a name/documentation group may carry several (multi-language authoring)."""

    text: str
    lang: str | None = None


@dataclass(frozen=True)
class ExchangeProperty:
    property_definition_ref: str
    values: tuple[LangString, ...] = ()


@dataclass(frozen=True)
class ExchangePropertyDefinition:
    identifier: str
    data_type: str  # DataType enum: string|boolean|currency|date|time|number
    names: tuple[LangString, ...] = ()


@dataclass(frozen=True)
class ExchangeElement:
    identifier: str
    concept_type: str  # the xsi:type value, e.g. "BusinessActor"
    names: tuple[LangString, ...] = ()
    documentation: tuple[LangString, ...] = ()
    properties: tuple[ExchangeProperty, ...] = ()


@dataclass(frozen=True)
class ExchangeRelationship:
    identifier: str
    concept_type: str  # the xsi:type value, e.g. "Assignment"
    source: str
    target: str
    names: tuple[LangString, ...] = ()
    documentation: tuple[LangString, ...] = ()
    properties: tuple[ExchangeProperty, ...] = ()


@dataclass(frozen=True)
class ExchangeModel:
    identifier: str
    names: tuple[LangString, ...] = ()
    documentation: tuple[LangString, ...] = ()
    properties: tuple[ExchangeProperty, ...] = ()
    elements: tuple[ExchangeElement, ...] = ()
    relationships: tuple[ExchangeRelationship, ...] = ()
    property_definitions: tuple[ExchangePropertyDefinition, ...] = ()

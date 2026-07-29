"""C19C v3.1 model-exchange reader (D10, parent plan §4.5, WU-F2): defusedxml-gated,
optionally XSD-validated, extraction into the codec-neutral ``ExchangeModel`` shape.
Concrete-type -> ArchiMate 4 mapping is WU-F3a's job, not this reader's.
"""

from __future__ import annotations

from lxml import etree

from src.application.exchange.document import (
    ExchangeElement,
    ExchangeModel,
    ExchangeProperty,
    ExchangePropertyDefinition,
    ExchangeRelationship,
    LangString,
)
from src.application.exchange.ports import ExchangeDocumentError
from src.infrastructure.exchange.archimate_model_exchange._xml_safety import (
    defuse_and_parse,
    validate_against_schema,
)

MODEL_NS = "http://www.opengroup.org/xsd/archimate/3.0/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
XML_NS = "http://www.w3.org/XML/1998/namespace"

_XSI_TYPE = f"{{{XSI_NS}}}type"
_XML_LANG = f"{{{XML_NS}}}lang"


def _tag(name: str) -> str:
    return f"{{{MODEL_NS}}}{name}"


def _lang_strings(parent: etree._Element, tag: str) -> tuple[LangString, ...]:
    return tuple(
        LangString(text=child.text or "", lang=child.get(_XML_LANG))
        for child in parent.findall(_tag(tag))
    )


def _properties(parent: etree._Element) -> tuple[ExchangeProperty, ...]:
    properties_el = parent.find(_tag("properties"))
    if properties_el is None:
        return ()
    return tuple(
        ExchangeProperty(
            property_definition_ref=prop_el.get("propertyDefinitionRef", ""),
            values=_lang_strings(prop_el, "value"),
        )
        for prop_el in properties_el.findall(_tag("property"))
    )


def _concept_type(el: etree._Element) -> str:
    # Strips an xsi:type namespace prefix, e.g. "archimate:BusinessActor" -> "BusinessActor".
    return el.get(_XSI_TYPE, "").split(":", 1)[-1]


def _element(el: etree._Element) -> ExchangeElement:
    return ExchangeElement(
        identifier=el.get("identifier", ""),
        concept_type=_concept_type(el),
        names=_lang_strings(el, "name"),
        documentation=_lang_strings(el, "documentation"),
        properties=_properties(el),
    )


def _relationship(el: etree._Element) -> ExchangeRelationship:
    return ExchangeRelationship(
        identifier=el.get("identifier", ""),
        concept_type=_concept_type(el),
        source=el.get("source", ""),
        target=el.get("target", ""),
        names=_lang_strings(el, "name"),
        documentation=_lang_strings(el, "documentation"),
        properties=_properties(el),
    )


def _property_definition(el: etree._Element) -> ExchangePropertyDefinition:
    return ExchangePropertyDefinition(
        identifier=el.get("identifier", ""),
        data_type=el.get("type", "string"),
        names=_lang_strings(el, "name"),
    )


class ArchimateModelExchangeReader:
    """Reads a C19C v3.1 model-exchange document into an ``ExchangeModel``.

    ``schema_path`` is injected, not looked up at a fixed location: the reviewed Q3
    decision fetches the XSD at dev/test time only (gitignored, never committed), so this
    codec has no business assuming where — or whether — a schema is available at any
    given caller's runtime. ``None`` skips schema validation (XXE/size/well-formedness
    defenses still apply); the actual production schema-sourcing strategy is WU-F3a/F4's
    wiring concern.
    """

    def __init__(self, schema_path: str | None = None) -> None:
        self._schema_path = schema_path

    def read(self, source: bytes) -> ExchangeModel:
        root = defuse_and_parse(source)
        if root.tag != _tag("model"):
            raise ExchangeDocumentError(f"expected a <model> root element, found {root.tag!r}")
        if self._schema_path is not None:
            validate_against_schema(root, self._schema_path)

        elements_el = root.find(_tag("elements"))
        relationships_el = root.find(_tag("relationships"))
        property_definitions_el = root.find(_tag("propertyDefinitions"))

        return ExchangeModel(
            identifier=root.get("identifier", ""),
            names=_lang_strings(root, "name"),
            documentation=_lang_strings(root, "documentation"),
            properties=_properties(root),
            elements=(
                tuple(_element(el) for el in elements_el.findall(_tag("element")))
                if elements_el is not None else ()
            ),
            relationships=(
                tuple(_relationship(el) for el in relationships_el.findall(_tag("relationship")))
                if relationships_el is not None else ()
            ),
            property_definitions=(
                tuple(
                    _property_definition(el)
                    for el in property_definitions_el.findall(_tag("propertyDefinition"))
                )
                if property_definitions_el is not None else ()
            ),
        )

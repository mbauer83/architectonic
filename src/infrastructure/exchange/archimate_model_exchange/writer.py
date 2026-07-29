"""C19C v3.1 model-exchange writer (D10, parent plan §4.5, WU-F2): serializes an
``ExchangeModel`` back to a schema-shaped XML document — the writer half of the WU-F2
round-trip; ArchiMate 4 -> concrete-3.x-type mapping is WU-F3b's job, not this writer's.

Element order follows ``ModelType``'s XSD sequence (name(s), documentation, properties,
[metadata], elements, relationships, [organizations], propertyDefinitions) — the bracketed
steps are out of WU-F2 scope (see ``document.py``) and simply omitted; every XSD-mandated
step this writer does emit stays in its required relative order.
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

MODEL_NS = "http://www.opengroup.org/xsd/archimate/3.0/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
XML_NS = "http://www.w3.org/XML/1998/namespace"

_XSI_TYPE = f"{{{XSI_NS}}}type"
_XML_LANG = f"{{{XML_NS}}}lang"


def _tag(name: str) -> str:
    return f"{{{MODEL_NS}}}{name}"


def _append_lang_strings(parent: etree._Element, tag: str, values: tuple[LangString, ...]) -> None:
    for value in values:
        child = etree.SubElement(parent, _tag(tag))
        child.text = value.text
        if value.lang is not None:
            child.set(_XML_LANG, value.lang)


def _append_properties(parent: etree._Element, properties: tuple[ExchangeProperty, ...]) -> None:
    if not properties:
        return
    properties_el = etree.SubElement(parent, _tag("properties"))
    for prop in properties:
        prop_el = etree.SubElement(properties_el, _tag("property"))
        prop_el.set("propertyDefinitionRef", prop.property_definition_ref)
        _append_lang_strings(prop_el, "value", prop.values)


def _append_element(parent: etree._Element, element: ExchangeElement) -> None:
    el = etree.SubElement(parent, _tag("element"))
    el.set("identifier", element.identifier)
    el.set(_XSI_TYPE, element.concept_type)
    _append_lang_strings(el, "name", element.names)
    _append_lang_strings(el, "documentation", element.documentation)
    _append_properties(el, element.properties)


def _append_relationship(parent: etree._Element, relationship: ExchangeRelationship) -> None:
    el = etree.SubElement(parent, _tag("relationship"))
    el.set("identifier", relationship.identifier)
    el.set(_XSI_TYPE, relationship.concept_type)
    el.set("source", relationship.source)
    el.set("target", relationship.target)
    _append_lang_strings(el, "name", relationship.names)
    _append_lang_strings(el, "documentation", relationship.documentation)
    _append_properties(el, relationship.properties)


def _append_property_definition(parent: etree._Element, definition: ExchangePropertyDefinition) -> None:
    el = etree.SubElement(parent, _tag("propertyDefinition"))
    el.set("identifier", definition.identifier)
    el.set("type", definition.data_type)
    _append_lang_strings(el, "name", definition.names)


class ArchimateModelExchangeWriter:
    """Serializes an ``ExchangeModel`` to a C19C v3.1 model-exchange document."""

    def write(self, model: ExchangeModel) -> bytes:
        root = etree.Element(_tag("model"), nsmap={None: MODEL_NS, "xsi": XSI_NS})
        root.set("identifier", model.identifier)
        _append_lang_strings(root, "name", model.names)
        _append_lang_strings(root, "documentation", model.documentation)
        _append_properties(root, model.properties)

        if model.elements:
            elements_el = etree.SubElement(root, _tag("elements"))
            for element in model.elements:
                _append_element(elements_el, element)

        if model.relationships:
            relationships_el = etree.SubElement(root, _tag("relationships"))
            for relationship in model.relationships:
                _append_relationship(relationships_el, relationship)

        if model.property_definitions:
            property_definitions_el = etree.SubElement(root, _tag("propertyDefinitions"))
            for definition in model.property_definitions:
                _append_property_definition(property_definitions_el, definition)

        return etree.tostring(root, xml_declaration=True, encoding="UTF-8")

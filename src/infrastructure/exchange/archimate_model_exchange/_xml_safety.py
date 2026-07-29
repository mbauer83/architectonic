"""Shared XXE/size-cap defenses for the model-exchange codec (D10, parent plan §4.5).

Two layers, deliberately not one: ``defusedxml.ElementTree`` is the actively-maintained
core of the defusedxml project and is used purely as a rejection gate for a forbidden
DTD/entity (billion-laughs, XXE) — its own tree is discarded. ``defusedxml.lxml`` is NOT
used: upstream has deprecated it (schema validation needs lxml, which ``defusedxml.
ElementTree`` cannot do), so the real extraction tree is built with ``lxml.etree`` configured
with its own hardened parser flags (``resolve_entities=False``, ``no_network=True``, DTDs
never loaded) — equally safe, without the deprecated wrapper.
"""

from __future__ import annotations

import io
from xml.etree.ElementTree import ParseError as ElementTreeParseError

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import parse as defused_parse
from lxml import etree

from src.application.exchange.ports import ExchangeDocumentError
from src.config.settings import exchange_max_document_bytes


def defuse_and_parse(source: bytes) -> etree._Element:
    """Reject oversize input and any forbidden DTD/entity before building a real tree;
    return a safely-parsed lxml root. Raises ``ExchangeDocumentError`` for any input this
    codec must reject — never returns a partial tree for rejected input."""
    max_bytes = exchange_max_document_bytes()
    if len(source) > max_bytes:
        raise ExchangeDocumentError(f"document exceeds the {max_bytes}-byte size cap")

    try:
        defused_parse(io.BytesIO(source), forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except DefusedXmlException as exc:
        raise ExchangeDocumentError(f"rejected unsafe XML: {exc}") from exc
    except ElementTreeParseError as exc:
        raise ExchangeDocumentError(f"malformed XML: {exc}") from exc

    parser = etree.XMLParser(
        resolve_entities=False, no_network=True, load_dtd=False, dtd_validation=False, huge_tree=False,
    )
    try:
        return etree.fromstring(source, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise ExchangeDocumentError(f"malformed XML: {exc}") from exc


_XML_NAMESPACE_XSD_URL = "http://www.w3.org/2001/xml.xsd"

# The C19C model XSD imports the standard W3C "xml" namespace schema (for xml:lang) by
# this well-known URL. libxml2 refuses network entity loading by default (correctly, for
# untrusted input) — so schema *compilation* would otherwise depend on the network being
# reachable and w3.org being up. This is a minimal, self-authored stand-in providing only
# the one attribute the model XSD actually references (`xml:lang`) — not a copy of the
# real W3C file — so schema loading is fully local and deterministic.
_XML_NAMESPACE_XSD_STUB = b"""<?xml version="1.0"?>
<xs:schema targetNamespace="http://www.w3.org/XML/1998/namespace"
           xmlns:xs="http://www.w3.org/2001/XMLSchema"
           elementFormDefault="qualified">
  <xs:attribute name="lang" type="xs:language"/>
</xs:schema>
"""


class _LocalXmlNamespaceResolver(etree.Resolver):
    def resolve(self, url: str, pubid: object, context: object) -> object:
        if url == _XML_NAMESPACE_XSD_URL:
            return self.resolve_string(_XML_NAMESPACE_XSD_STUB, context)
        return None


def validate_against_schema(root: etree._Element, schema_path: str) -> None:
    """Validate ``root`` against the C19C model XSD at ``schema_path`` (dev-time-fetched,
    never committed — see ``tools/model_exchange/fetch_c19c_xsds.sh``). Raises ``ExchangeDocumentError``
    listing every violation; callers decide whether a schema is available at all (WU-F2
    scope: the codec never assumes a fixed runtime location for the XSD)."""
    schema_parser = etree.XMLParser()
    schema_parser.resolvers.add(_LocalXmlNamespaceResolver())
    schema_doc = etree.parse(schema_path, parser=schema_parser)
    schema = etree.XMLSchema(schema_doc)
    if schema.validate(root):
        return
    errors = "; ".join(str(entry) for entry in schema.error_log)
    raise ExchangeDocumentError(f"schema validation failed: {errors}")

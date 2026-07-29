"""XSD schema-validation tests for ``ArchimateModelExchangeReader`` (D10, WU-F2).

The real C19C model XSD is never committed (WU-F1's reviewed Q3 decision) — these tests
run only when a developer has locally fetched it via ``tools/model_exchange/fetch_c19c_xsds.sh`` into the
gitignored ``spec/c19c-xsd/`` directory, and skip (not fail) otherwise, so the suite stays
green in a fresh checkout/CI with no network access to The Open Group.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.exchange.ports import ExchangeDocumentError
from src.infrastructure.exchange.archimate_model_exchange import ArchimateModelExchangeReader

_NS = "http://www.opengroup.org/xsd/archimate/3.0/"
_XSI = "http://www.w3.org/2001/XMLSchema-instance"
_SCHEMA_PATH = Path(__file__).parent.parent.parent.parent.parent / "spec" / "c19c-xsd" / "archimate3_Model.xsd"

pytestmark = pytest.mark.skipif(
    not _SCHEMA_PATH.exists(),
    reason="C19C model XSD not fetched locally — run tools/model_exchange/fetch_c19c_xsds.sh "
    "for schema-validation coverage",
)


def _reader() -> ArchimateModelExchangeReader:
    return ArchimateModelExchangeReader(schema_path=str(_SCHEMA_PATH))


class TestSchemaValid:
    def test_a_well_formed_synthetic_document_passes(self) -> None:
        payload = (
            f'<model xmlns="{_NS}" xmlns:xsi="{_XSI}" identifier="m1">'
            '<name xml:lang="en">Synthetic Test Model</name>'
            '<elements>'
            '<element identifier="e1" xsi:type="BusinessActor"><name>A</name></element>'
            '<element identifier="e2" xsi:type="BusinessRole"><name>B</name></element>'
            '</elements>'
            '<relationships>'
            '<relationship identifier="r1" source="e1" target="e2" xsi:type="Assignment">'
            '<name>Assigns</name></relationship>'
            '</relationships>'
            '</model>'
        ).encode()
        model = _reader().read(payload)
        assert model.identifier == "m1"
        assert len(model.elements) == 2
        assert len(model.relationships) == 1


class TestSchemaInvalid:
    def test_element_missing_required_identifier_is_rejected(self) -> None:
        payload = (
            f'<model xmlns="{_NS}" xmlns:xsi="{_XSI}" identifier="m1">'
            '<elements><element xsi:type="BusinessActor"><name>A</name></element></elements>'
            '</model>'
        ).encode()
        with pytest.raises(ExchangeDocumentError, match="schema validation failed"):
            _reader().read(payload)

    def test_relationship_referencing_an_unknown_source_is_rejected(self) -> None:
        payload = (
            f'<model xmlns="{_NS}" xmlns:xsi="{_XSI}" identifier="m1">'
            '<elements><element identifier="e1" xsi:type="BusinessActor"><name>A</name></element></elements>'
            '<relationships>'
            '<relationship identifier="r1" source="does-not-exist" target="e1" xsi:type="Assignment"/>'
            '</relationships>'
            '</model>'
        ).encode()
        with pytest.raises(ExchangeDocumentError, match="schema validation failed"):
            _reader().read(payload)

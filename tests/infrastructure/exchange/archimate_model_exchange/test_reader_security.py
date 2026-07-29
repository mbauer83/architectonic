"""Security-boundary tests for ``ArchimateModelExchangeReader`` (D10, WU-F2): malformed,
oversize, and XXE/entity-expansion fixtures must be rejected, never silently degraded.
"""

from __future__ import annotations

import pytest

from src.application.exchange.ports import ExchangeDocumentError
from src.infrastructure.exchange.archimate_model_exchange import ArchimateModelExchangeReader

_NS = "http://www.opengroup.org/xsd/archimate/3.0/"


def _model(body: str) -> bytes:
    return f'<model xmlns="{_NS}" identifier="m1">{body}</model>'.encode()


class TestMalformedXml:
    def test_mismatched_tag_is_rejected(self) -> None:
        with pytest.raises(ExchangeDocumentError, match="malformed"):
            ArchimateModelExchangeReader().read(b"<model><unterminated></model>")

    def test_empty_input_is_rejected(self) -> None:
        with pytest.raises(ExchangeDocumentError, match="malformed"):
            ArchimateModelExchangeReader().read(b"")

    def test_wrong_root_element_is_rejected(self) -> None:
        with pytest.raises(ExchangeDocumentError, match="model"):
            ArchimateModelExchangeReader().read(f'<notamodel xmlns="{_NS}"/>'.encode())


class TestXxeAndEntityExpansion:
    def test_external_entity_xxe_is_rejected(self) -> None:
        payload = (
            "<?xml version='1.0'?>"
            '<!DOCTYPE model [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            f'<model xmlns="{_NS}" identifier="m1"><name>&xxe;</name></model>'
        ).encode()
        with pytest.raises(ExchangeDocumentError):
            ArchimateModelExchangeReader().read(payload)

    def test_internal_entity_billion_laughs_is_rejected(self) -> None:
        payload = (
            "<?xml version='1.0'?>"
            "<!DOCTYPE model [<!ENTITY a \"lol\"><!ENTITY b \"&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;\">]>"
            f'<model xmlns="{_NS}" identifier="m1"><name>&b;</name></model>'
        ).encode()
        with pytest.raises(ExchangeDocumentError):
            ArchimateModelExchangeReader().read(payload)

    def test_bare_doctype_with_no_entities_is_still_rejected(self) -> None:
        """Legitimate C19C documents never carry a DOCTYPE at all — reject outright
        rather than trying to distinguish a "harmless" DOCTYPE from a dangerous one."""
        payload = f'<?xml version="1.0"?><!DOCTYPE model><model xmlns="{_NS}" identifier="m1"/>'.encode()
        with pytest.raises(ExchangeDocumentError):
            ArchimateModelExchangeReader().read(payload)


class TestSizeCap:
    def test_oversize_document_is_rejected_before_parsing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "src.infrastructure.exchange.archimate_model_exchange._xml_safety.exchange_max_document_bytes",
            lambda: 64,
        )
        oversize = _model("<name>" + ("x" * 200) + "</name>")
        assert len(oversize) > 64
        with pytest.raises(ExchangeDocumentError, match="size cap"):
            ArchimateModelExchangeReader().read(oversize)

    def test_document_within_the_cap_is_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "src.infrastructure.exchange.archimate_model_exchange._xml_safety.exchange_max_document_bytes",
            lambda: 10_000,
        )
        model = ArchimateModelExchangeReader().read(_model("<name>Small</name>"))
        assert model.identifier == "m1"

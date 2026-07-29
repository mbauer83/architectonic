"""Application-defined codec ports (parent plan §4.5, WU-F2): the narrow reader/writer pair
``import_model``/``export_model`` (WU-F3a/F3b) will depend on, implemented by the
infrastructure adapter in ``src/infrastructure/exchange/archimate_model_exchange/``.
"""

from __future__ import annotations

from typing import Protocol

from src.application.exchange.document import ExchangeModel


class ExchangeDocumentError(Exception):
    """Raised for any input a reader must reject: malformed XML, a forbidden DTD/entity
    (XXE/entity-expansion attempt), oversize input, or a schema-validation failure."""


class ExchangeDocumentReader(Protocol):
    def read(self, source: bytes) -> ExchangeModel:
        """Parse a C19C model-exchange document. Raises ``ExchangeDocumentError`` for any
        input that is malformed, oversize, schema-invalid, or carries a forbidden
        DTD/entity — never returns a partial result for such input."""
        ...


class ExchangeDocumentWriter(Protocol):
    def write(self, model: ExchangeModel) -> bytes:
        """Serialize an ``ExchangeModel`` to a C19C model-exchange document."""
        ...

"""Import C19C exchange documents through the engagement write queue."""
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException

from src.application.exchange.import_model import ImportedConnection, ImportedEntity, ImportReport, UnmappableItem
from src.application.exchange.ports import ExchangeDocumentError
from src.infrastructure.exchange.archimate_model_exchange import ArchimateModelExchangeReader
from src.infrastructure.exchange.archimate_model_exchange.import_service import import_document
from src.infrastructure.rest.contracts.wire_shape import Closed
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._failures import rejected_input
from src.infrastructure.rest.routers._openapi import TAG_ENTITIES, WRITE_RESPONSES

router = APIRouter()


class ExchangeImportResponse(Closed):
    committed: bool
    entities: tuple[ImportedEntity, ...]
    connections: tuple[ImportedConnection, ...]
    unmappable: tuple[UnmappableItem, ...]


@router.post("/api/exchange-imports", tags=[TAG_ENTITIES],
             summary="Import an ArchiMate model exchange document into the engagement",
             response_model=ExchangeImportResponse, responses=WRITE_RESPONSES)
def import_exchange(content: Annotated[bytes, Body(media_type="application/xml")]) -> ImportReport:
    root = s.maybe_engagement_root()
    if root is None:
        raise HTTPException(503, "Engagement repository is not initialised")
    try:
        document = ArchimateModelExchangeReader().read(content)
    except ExchangeDocumentError as exc:
        raise rejected_input(str(exc), field="content") from exc
    return s.authorized_write(
        "entities_import_model", import_document, root, document, commit=True, clear_caches=s.clear_caches,
    )

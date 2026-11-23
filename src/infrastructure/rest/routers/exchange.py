"""Import C19C exchange documents through the engagement write queue."""
from typing import Annotated

from fastapi import APIRouter, Body, Depends

from src.application.exchange.import_model import ImportedConnection, ImportedEntity, ImportReport, UnmappableItem
from src.application.exchange.ports import ExchangeDocumentError
from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.exchange.archimate_model_exchange import ArchimateModelExchangeReader
from src.infrastructure.exchange.archimate_model_exchange.write_adapter import ArtifactWriteExchangeAdapter
from src.infrastructure.rest.contracts.wire_shape import Closed
from src.infrastructure.rest.dependencies import runtime_catalogs_dependency
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
def import_exchange(
    content: Annotated[bytes, Body(media_type="application/xml")],
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> ImportReport:
    try:
        document = ArchimateModelExchangeReader().read(content)
    except ExchangeDocumentError as exc:
        raise rejected_input(str(exc), field="content") from exc
    root, _, verifier = s.get_write_deps(catalogs)
    writer = ArtifactWriteExchangeAdapter(root, verifier=verifier, clear_caches=s.clear_caches)
    return s.authorized_write("entities_import_model", writer.import_document, document, commit=True)

"""Compose the exchange import on the selected engagement, including its local identity map."""
from collections.abc import Callable
from pathlib import Path

from src.application.exchange.document import ExchangeModel
from src.application.exchange.import_model import ImportReport, import_model
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.exchange.archimate_model_exchange.concept_mapping import DeclarativeConceptMapper
from src.infrastructure.exchange.archimate_model_exchange.identity_store import RepoExchangeIdentityStore
from src.infrastructure.exchange.archimate_model_exchange.write_adapter import ArtifactWriteExchangeAdapter


def import_document(
    root: Path, document: ExchangeModel, *, commit: bool, clear_caches: Callable[[Path], None] | None = None,
) -> ImportReport:
    return import_model(document, store=ArtifactRegistry(shared_artifact_index(root)),
                        identity=RepoExchangeIdentityStore(root), mapper=DeclarativeConceptMapper(),
                        writer=ArtifactWriteExchangeAdapter(root, clear_caches=clear_caches), commit=commit)

"""Implements ``ExchangeArtifactWriter`` (D10, parent plan §4.5, WU-F3a) over the same
``artifact_write`` layer the GUI and MCP tools use — no raw file emission, same
validation/verifier path.
"""

from __future__ import annotations

from pathlib import Path

from src.application.exchange.write_ports import ExchangeWriteOutcome, InvalidRelationshipError
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.domain.repository.groups import UNCATEGORIZED
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.verification.verifier_factory import build_artifact_verifier
from src.infrastructure.write import artifact_write_ops
from src.infrastructure.write.artifact_write.types import WriteResult

_NOT_PERMITTED_MARKER = "is not permitted from"


def _outcome(result: WriteResult) -> ExchangeWriteOutcome:
    verification: dict[str, object] = result.verification or {}
    valid = bool(verification.get("valid", True))
    return ExchangeWriteOutcome(
        wrote=result.wrote,
        artifact_id=result.artifact_id,
        valid=valid,
        warnings=tuple(result.warnings),
    )


class ArtifactWriteExchangeAdapter:
    def __init__(self, repo_root: Path, *, group: str = UNCATEGORIZED) -> None:
        self._repo_root = repo_root
        self._group = group
        self._registry = ArtifactRegistry(shared_artifact_index([repo_root]))
        self._verifier = build_artifact_verifier(self._registry, catalogs=build_runtime_catalogs(get_module_registry()))

    def _clear_caches(self, _path: Path) -> None:
        self._registry.refresh()

    def create_entity(
        self,
        *,
        artifact_type: str,
        name: str,
        properties: dict[str, str],
        notes: str | None,
        specialization: str | None,
        dry_run: bool,
    ) -> ExchangeWriteOutcome:
        result = artifact_write_ops.create_entity(
            repo_root=self._repo_root,
            verifier=self._verifier,
            clear_repo_caches=self._clear_caches,
            artifact_type=artifact_type,
            name=name,
            summary=None,
            properties=properties,
            notes=notes,
            specialization=specialization,
            artifact_id=None,
            version="0.1.0",
            status="draft",
            last_updated=None,
            dry_run=dry_run,
            group=self._group,
        )
        return _outcome(result)

    def update_entity(
        self,
        *,
        artifact_id: str,
        name: str,
        properties: dict[str, str],
        notes: str | None,
        specialization: str | None,
        dry_run: bool,
    ) -> ExchangeWriteOutcome:
        result = artifact_write_ops.edit_entity(
            repo_root=self._repo_root,
            registry=self._registry,
            verifier=self._verifier,
            clear_repo_caches=self._clear_caches,
            artifact_id=artifact_id,
            name=name,
            properties=properties,
            notes=notes,
            specialization=specialization,
            dry_run=dry_run,
        )
        return _outcome(result)

    def add_connection(
        self,
        *,
        source: str,
        target: str,
        connection_type: str,
        description: str | None,
        specialization: str | None,
        src_multiplicity: str | None,
        tgt_multiplicity: str | None,
        extra_known_ids: frozenset[str],
        dry_run: bool,
    ) -> ExchangeWriteOutcome:
        try:
            result = artifact_write_ops.add_connection(
                repo_root=self._repo_root,
                registry=self._registry,
                verifier=self._verifier,
                clear_repo_caches=self._clear_caches,
                source_entity=source,
                connection_type=connection_type,
                target_entity=target,
                description=description,
                version="0.1.0",
                status="draft",
                last_updated=None,
                dry_run=dry_run,
                src_multiplicity=src_multiplicity,
                tgt_multiplicity=tgt_multiplicity,
                specialization=specialization,
                extra_known_ids=extra_known_ids,
            )
        except ValueError as exc:
            if _NOT_PERMITTED_MARKER in str(exc):
                raise InvalidRelationshipError(str(exc)) from exc
            raise
        return _outcome(result)

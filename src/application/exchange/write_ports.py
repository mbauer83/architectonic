"""Write-side port for the exchange import use case (D10, parent plan §4.5, WU-F3a).

``import_model.py`` never emits raw files: every entity/connection it creates or updates
goes through this port, implemented in infrastructure as a thin wrapper over the same
``artifact_write`` layer the GUI and MCP tools use (same validation, same verifier).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class InvalidRelationshipError(Exception):
    """Raised when the underlying write layer rejects a connection type between the
    resolved source/target entity types (ArchiMate 4 permitted-relationship rules).
    The import use case reacts to this by falling back to ``archimate-association``
    for every relationship type except composition, which is never downgraded."""


@dataclass(frozen=True)
class ExchangeWriteOutcome:
    wrote: bool
    artifact_id: str
    valid: bool
    warnings: tuple[str, ...] = ()


class ExchangeArtifactWriter(Protocol):
    def create_entity(
        self,
        *,
        artifact_type: str,
        name: str,
        properties: dict[str, str],
        notes: str | None,
        specialization: str | None,
        dry_run: bool,
    ) -> ExchangeWriteOutcome: ...

    def update_entity(
        self,
        *,
        artifact_id: str,
        name: str,
        properties: dict[str, str],
        notes: str | None,
        specialization: str | None,
        dry_run: bool,
    ) -> ExchangeWriteOutcome: ...

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
        """Raises ``InvalidRelationshipError`` when the connection type is not permitted
        between the resolved source/target entity types. ``extra_known_ids`` lets a
        dry-run batch reference sibling entities proposed earlier in the same run that
        have not been written to disk yet."""
        ...

from __future__ import annotations

from pathlib import Path
from typing import Literal

from src.application.ports import ReadableArtifactStore
from src.application.read_models import EntityContextReadModel
from src.domain.ontology_representation.artifact_types import (
    ArtifactSummary,
    ConnectionRecord,
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
)

from ._combined_support import first_not_none, merge_counter_dicts


class CombinedLookupMixin:
    """ArtifactLookup — try-engagement-then-enterprise fallback for single-artifact reads."""

    _engagement: ReadableArtifactStore
    _enterprise: ReadableArtifactStore

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return first_not_none(
            self._engagement.get_entity(artifact_id),
            lambda: self._enterprise.get_entity(artifact_id),
        )

    def get_connection(self, artifact_id: str) -> ConnectionRecord | None:
        return first_not_none(
            self._engagement.get_connection(artifact_id),
            lambda: self._enterprise.get_connection(artifact_id),
        )

    def get_diagram(self, artifact_id: str) -> DiagramRecord | None:
        return first_not_none(
            self._engagement.get_diagram(artifact_id),
            lambda: self._enterprise.get_diagram(artifact_id),
        )

    def get_document(self, artifact_id: str) -> DocumentRecord | None:
        return first_not_none(
            self._engagement.get_document(artifact_id),
            lambda: self._enterprise.get_document(artifact_id),
        )

    def read_artifact(
        self,
        artifact_id: str,
        *,
        mode: Literal["summary", "full"] = "summary",
        section: str | None = None,
    ) -> dict[str, object] | None:
        return first_not_none(
            self._engagement.read_artifact(artifact_id, mode=mode, section=section),
            lambda: self._enterprise.read_artifact(artifact_id, mode=mode, section=section),
        )

    def summarize_artifact(self, artifact_id: str) -> ArtifactSummary | None:
        return first_not_none(
            self._engagement.summarize_artifact(artifact_id),
            lambda: self._enterprise.summarize_artifact(artifact_id),
        )

    def read_entity_context(self, artifact_id: str) -> EntityContextReadModel | None:
        return first_not_none(
            self._engagement.read_entity_context(artifact_id),
            lambda: self._enterprise.read_entity_context(artifact_id),
        )

    def find_file_by_id(self, artifact_id: str) -> Path | None:
        return first_not_none(
            self._engagement.find_file_by_id(artifact_id),
            lambda: self._enterprise.find_file_by_id(artifact_id),
        )

    def stats(self) -> dict[str, object]:
        return merge_counter_dicts(self._engagement.stats(), self._enterprise.stats())

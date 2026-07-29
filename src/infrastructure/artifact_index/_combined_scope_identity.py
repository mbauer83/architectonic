from __future__ import annotations

from pathlib import Path
from typing import Literal

from src.application.ports import Candidate, ReadableArtifactStore

from ._combined_support import first_not_none


class CombinedScopeIdentityMixin:
    _engagement: ReadableArtifactStore
    _enterprise: ReadableArtifactStore

    def scope_for_path(self, path: Path) -> Literal["enterprise", "engagement", "unknown"]:
        scope = self._engagement.scope_for_path(path)
        return scope if scope != "unknown" else self._enterprise.scope_for_path(path)

    def scope_of_entity(self, artifact_id: str) -> Literal["enterprise", "engagement", "unknown"]:
        scope = self._engagement.scope_of_entity(artifact_id)
        return scope if scope != "unknown" else self._enterprise.scope_of_entity(artifact_id)

    def scope_of_connection(self, artifact_id: str) -> Literal["enterprise", "engagement", "unknown"]:
        scope = self._engagement.scope_of_connection(artifact_id)
        return scope if scope != "unknown" else self._enterprise.scope_of_connection(artifact_id)

    def entity_status(self, artifact_id: str) -> str | None:
        return first_not_none(
            self._engagement.entity_status(artifact_id),
            lambda: self._enterprise.entity_status(artifact_id),
        )

    def entity_statuses(self) -> dict[str, str]:
        return {**self._enterprise.entity_statuses(), **self._engagement.entity_statuses()}

    def connection_status(self, artifact_id: str) -> str | None:
        return first_not_none(
            self._engagement.connection_status(artifact_id),
            lambda: self._enterprise.connection_status(artifact_id),
        )

    def entity_ids(self) -> set[str]:
        return self._engagement.entity_ids() | self._enterprise.entity_ids()

    def connection_ids(self) -> set[str]:
        return self._engagement.connection_ids() | self._enterprise.connection_ids()

    def enterprise_entity_ids(self) -> set[str]:
        return self._enterprise.entity_ids()

    def engagement_entity_ids(self) -> set[str]:
        return self._engagement.entity_ids()

    def enterprise_connection_ids(self) -> set[str]:
        return self._enterprise.connection_ids()

    def engagement_connection_ids(self) -> set[str]:
        return self._engagement.connection_ids()

    def enterprise_document_ids(self) -> set[str]:
        return self._enterprise.enterprise_document_ids()

    def enterprise_diagram_ids(self) -> set[str]:
        return self._enterprise.enterprise_diagram_ids()

    def find_all_by_stable_id(self, short: str) -> list[Candidate]:
        return [*self._engagement.find_all_by_stable_id(short), *self._enterprise.find_all_by_stable_id(short)]

    def reconcile_short_id(self, short: str) -> None:
        self._engagement.reconcile_short_id(short)
        self._enterprise.reconcile_short_id(short)

    def scan_duplicate_short_ids(self) -> dict[str, list[Path]]:
        out = {key: list(value) for key, value in self._engagement.scan_duplicate_short_ids().items()}
        for key, paths in self._enterprise.scan_duplicate_short_ids().items():
            out.setdefault(key, []).extend(paths)
        return out

    def cross_repo_duplicate_ids(self) -> set[str]:
        """Full artifact_ids present in both canonical repos.

        `scan_duplicate_short_ids` only ever reports a *within-scope* duplicate (each
        canonical instance's own identity scan deliberately ignores cross-scope copies,
        since promotion's copy-then-unlink sequence legitimately produces one transiently)
        — so it can never see "exactly one file in engagement, exactly one in enterprise,
        same id" at all, whether that's a genuine full-id collision or a short id that
        happens to collide across repos with different full ids. Outside promotion (which
        never runs during startup), that state is not legitimate and must fail closed.
        """
        engagement_ids = (
            self._engagement.entity_ids()
            | self._engagement.connection_ids()
            | {r.artifact_id for r in self._engagement.list_diagrams()}
            | {r.artifact_id for r in self._engagement.list_documents()}
        )
        enterprise_ids = (
            self._enterprise.entity_ids()
            | self._enterprise.connection_ids()
            | {r.artifact_id for r in self._enterprise.list_diagrams()}
            | {r.artifact_id for r in self._enterprise.list_documents()}
        )
        return engagement_ids & enterprise_ids

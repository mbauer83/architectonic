"""Regression tests for slug-drift-tolerant self-exclusion in dedup checks (WS6).

A stale-slug or short-form ``exclude_artifact_id`` must still exclude the artifact
from its own duplicate check — identity is the stable short id, never the slug.
"""

from __future__ import annotations

from src.infrastructure.write.artifact_write._artifact_deduplication import (
    check_diagram_duplicate,
    check_document_duplicate,
    check_entity_duplicate,
)


def _entity(artifact_id: str) -> object:
    return _Rec(artifact_id)


class _Rec:
    def __init__(self, artifact_id: str) -> None:
        self.artifact_id = artifact_id


class _FakeRepo:
    def __init__(self, records: list[_Rec]) -> None:
        self._records = records

    def list_entities(self, artifact_type: str) -> list[_Rec]:
        return self._records

    def list_diagrams(self, diagram_type: str) -> list[_Rec]:
        return self._records

    def list_documents(self, doc_type: str) -> list[_Rec]:
        return self._records


_STORED = "APP@1712870400.Abc123.payments-service"
_SHORT = "APP@1712870400.Abc123"
_STALE = "APP@1712870400.Abc123.payments"  # an older slug for the same entity


def test_entity_self_excluded_with_stale_slug_exclude_id() -> None:
    """Excluding by a stale-slug id must not flag the entity as its own duplicate."""
    repo = _FakeRepo([_entity(_STORED)])
    dup = check_entity_duplicate(
        repo, "application-component", "payments-service", exclude_artifact_id=_STALE  # type: ignore[arg-type]
    )
    assert dup is None


def test_entity_self_excluded_with_short_form_exclude_id() -> None:
    repo = _FakeRepo([_entity(_STORED)])
    dup = check_entity_duplicate(
        repo, "application-component", "payments-service", exclude_artifact_id=_SHORT  # type: ignore[arg-type]
    )
    assert dup is None


def test_distinct_entity_still_detected_as_duplicate() -> None:
    """A genuinely different entity with the same slug is still a duplicate."""
    other = _entity("APP@9999999999.Zzz999.payments-service")
    repo = _FakeRepo([other])
    dup = check_entity_duplicate(
        repo, "application-component", "payments-service", exclude_artifact_id=_STALE  # type: ignore[arg-type]
    )
    assert dup is other


def test_diagram_and_document_self_excluded_with_stale_slug() -> None:
    repo = _FakeRepo([_entity(_STORED)])
    assert check_diagram_duplicate(
        repo, "archimate-application", "payments-service", exclude_artifact_id=_STALE  # type: ignore[arg-type]
    ) is None
    assert check_document_duplicate(
        repo, "standard", "payments-service", exclude_artifact_id=_STALE  # type: ignore[arg-type]
    ) is None

"""Aggregation (count/group-by) functions for ArtifactRepository."""

from __future__ import annotations

from typing import Literal

from src.application._artifact_query_helpers import single_or_none as _single_or_none
from src.application._artifact_query_helpers import summary_group_key as _summary_group_key
from src.application.ports import ReadableArtifactStore

_NONE_LABEL = "(none)"


def count_artifacts_by(
    store: ReadableArtifactStore,
    group_by: Literal["artifact_type", "diagram_type", "domain", "group"],
    *,
    artifact_type: str | list[str] | None = None,
    domain: str | list[str] | None = None,
    status: str | list[str] | None = None,
    include_connections: bool = True,
    include_diagrams: bool = True,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    if group_by == "diagram_type":
        for diag in store.list_diagrams(status=_single_or_none(status)):
            key = diag.diagram_type or _NONE_LABEL
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items()))
    if group_by == "domain":
        for ent in store.list_entities(
            artifact_type=_single_or_none(artifact_type),
            domain=_single_or_none(domain),
            status=_single_or_none(status),
        ):
            key = ent.domain or _NONE_LABEL
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items()))
    if group_by == "group":
        result: dict[str, int] = {}
        for ent in store.list_entities(artifact_type=_single_or_none(artifact_type), status=_single_or_none(status)):
            result[f"entities/{ent.group}"] = result.get(f"entities/{ent.group}", 0) + 1
        for diag in store.list_diagrams(status=_single_or_none(status)):
            result[f"diagrams/{diag.group}"] = result.get(f"diagrams/{diag.group}", 0) + 1
        for doc in store.list_documents(status=_single_or_none(status)):
            result[f"documents/{doc.group}"] = result.get(f"documents/{doc.group}", 0) + 1
        return dict(sorted(result.items()))
    for summary in store.list_artifacts(
        artifact_type=artifact_type,
        domain=domain,
        status=status,
        include_connections=include_connections,
        include_diagrams=include_diagrams,
    ):
        key = _summary_group_key(summary, group_by)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))

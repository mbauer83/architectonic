"""Synthesize a renderable ``ConnectionRecord`` for a derived (non-modeled)
relationship — never persisted or indexed, purely a rendering convenience so a derived
connection draws in its derived type's notation exactly like a modeled one, told apart
only by the synthetic id it already carries (``derived::<type>::<path-key>``, from the
relationship-derivation engine)."""

from __future__ import annotations

from pathlib import Path

from src.application.viewpoints.execution_result import ConnectionItemSummary
from src.domain.ontology_representation.artifact_types import ConnectionRecord
from src.domain.relationships.relationship_reachability import is_derived_connection_id as is_derived_connection_id

__all__ = ["derived_connection_record", "is_derived_connection_id"]


def derived_connection_record(summary: ConnectionItemSummary) -> ConnectionRecord:
    """Build a synthetic, renderer-only record from a derived connection's execution-
    result summary. Never written to disk or the artifact index. ``extra.certainty``
    lets the renderer distinguish certain from potential derivations visually."""
    return ConnectionRecord(
        artifact_id=summary.id,
        source=summary.source,
        target=summary.target,
        conn_type=summary.type,
        version="",
        status="",
        path=Path(),
        extra={"certainty": summary.certainty},
        content_text="",
    )

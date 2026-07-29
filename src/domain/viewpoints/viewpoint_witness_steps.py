"""Ordered witness steps for a derived connection.

A derived relationship's raw ``via_connection_ids`` are NOT guaranteed to be in
source-to-target traversal order (the derivation engine can extend a composed chain from
either end), so ID membership alone is not a readable path. This module reconstructs the
walk once, server-side: step N connects the chain's position N to position N+1, each step
carrying the real connection's identity, endpoints, type, and its orientation relative to
the walk. Ties (two remaining witness connections incident to the same position — not
producible by a single composed chain, but guarded anyway) break deterministically by
connection id, so the same input always renders the same path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.domain.ontology_representation.artifact_types import ConnectionRecord


@dataclass(frozen=True)
class WitnessStep:
    connection_id: str
    source: str
    target: str
    connection_type: str
    direction: Literal["forward", "reverse"]
    """``forward`` when the real connection's authored source is the chain position the
    walk arrived from; ``reverse`` when the walk traverses it against authored order."""
    hop_index: int


def order_witness_steps(
    chain_source: str,
    chain_target: str,
    connections: tuple[ConnectionRecord, ...],
) -> tuple[WitnessStep, ...]:
    """Walk from ``chain_source`` to ``chain_target`` consuming every witness connection
    exactly once. Returns () when the witnesses do not form one connected chain between
    the endpoints (e.g. a witness connection was deleted since derivation) — callers
    treat that as "chain unavailable", never as an empty-but-valid path."""
    remaining: dict[str, ConnectionRecord] = {record.artifact_id: record for record in connections}
    steps: list[WitnessStep] = []
    position = chain_source
    while remaining:
        candidates = sorted(
            (record for record in remaining.values() if position in (record.source, record.target)),
            key=lambda record: record.artifact_id,
        )
        if not candidates:
            return ()
        record = candidates[0]
        del remaining[record.artifact_id]
        forward = record.source == position
        steps.append(
            WitnessStep(
                connection_id=record.artifact_id,
                source=record.source,
                target=record.target,
                connection_type=record.conn_type,
                direction="forward" if forward else "reverse",
                hop_index=len(steps),
            )
        )
        position = record.target if forward else record.source
    return tuple(steps) if steps and position == chain_target else ()

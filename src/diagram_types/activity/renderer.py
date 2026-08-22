"""Activity diagram PUML renderer — graph-based, PlantUML Activity v2 (beta) syntax.

diagram_entities keys (entity type → flat list of items):
  swimlane:  [{id, label, entity_id?}]
  action:    [{id, label?, link?, entity_id?}]
  decision:  [{id, condition, then_label, else_label, entity_id?}]
  fork:      [{id, entity_id?}]
  partition: [{id, label?}]
  note:      [{id, text, side?}]

diagram_connections encodes all structure as local-ID connections:
  step-flow:        source → target  (sequential flow between steps / top-level ordering)
  step-then:        decision → first step of then-branch
  step-else:        decision → first step of else-branch
  step-fork-branch: fork → first step of each parallel branch (one conn per branch)
  step-contains:    partition → first step inside the partition
  step-in-lane:     step → swimlane
  step-note-of:     note → step

This module builds the indices and the preamble; `_emission` walks the graph and emits the body.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.ontology_representation.ontology_protocol import DiagramRendererReferences
from src.infrastructure.rendering.puml_label_wrapping import label_wrap_skinparams
from src.infrastructure.rendering.puml_safety import (
    configured_puml_size_warning_threshold,
    warn_when_puml_exceeds_threshold,
)

from ._connectors import Connectors, connector_names
from ._emission import (
    EmissionContext,
    LaneCursor,
    Swimlanes,
    emit_from,
    emit_orphans,
    puml_text,
)
from ._step_graph import StepGraph

_STEP_KEYS = ("action", "decision", "fork", "partition")


class ActivityPumlRenderer:
    def __init__(self, config: Mapping[str, Any]) -> None:
        self._config = dict(config)

    def render_body(
        self,
        name: str,
        entities: Sequence[EntityRecord],
        connections: Sequence[ConnectionRecord],
        diagram_type: str,
        repo_root: Path,
        *,
        diagram_entities: Mapping[str, object] | None = None,
        diagram_connections: list[dict[str, object]] | None = None,
    ) -> str:
        del diagram_type, entities, connections, repo_root
        diagram_name = re.sub(r"[^a-zA-Z0-9_-]", "-", name.lower()).strip("-") or "activity"
        kd = diagram_entities or {}
        kcs = diagram_connections or []

        graph = StepGraph(
            step_by_id=_build_step_by_id(kd),
            flow_next=_build_single_target(kcs, "step-flow"),
            then_target=_build_single_target(kcs, "step-then"),
            else_target=_build_single_target(kcs, "step-else"),
            fork_branches=_build_multi_target(kcs, "step-fork-branch"),
            contains_first=_build_single_target(kcs, "step-contains"),
        )
        branch_owned = _branch_owned_set(graph)

        lanes = _read_lanes(kd)
        lane_index = _build_single_target(kcs, "step-in-lane")

        root_id = _find_root(graph, branch_owned)
        initial_lane_id = lane_index.get(root_id) if root_id else None
        if initial_lane_id is None and lanes:
            initial_lane_id = lanes[0]["id"]

        lane_map = {lane["id"]: lane for lane in lanes}
        notes = _build_notes_index(kd, kcs)

        def walk(connectors: Connectors) -> list[str]:
            ctx = EmissionContext(
                graph=graph,
                lanes=Swimlanes(
                    index=lane_index,
                    by_id=lane_map,
                    declared=bool(lanes),
                    cursor=LaneCursor(current=initial_lane_id),
                ),
                notes=notes,
                connectors=connectors,
            )
            walked: list[str] = []
            visited: set[str] = set()
            if root_id:
                emit_from(root_id, ctx, walked, visited)
            # Whenever steps remain, not only when there was no root: a diagram may declare two
            # chains with no edge between them, and both are declared, so both are drawn.
            emit_orphans(branch_owned, ctx, walked, visited)
            return walked

        # A connector's entry half has to be drawn before the arrival that needs it, and only the
        # walk knows which steps are arrived at that way. So the walk runs twice: the first
        # discovers the arrivals, the second names them and draws both halves. A connector changes
        # no control flow, so the second walk meets the same arrivals as the first.
        discovery = Connectors()
        walk(discovery)
        body_lines = walk(Connectors(name_for=connector_names(discovery.arrivals)))

        lines: list[str] = [
            f"@startuml {diagram_name}",
            # Sentinel arch:// links wrap the step labels themselves (see _step_links) —
            # style hyperlinks as plain text so the anchor is invisible, not blue/underlined.
            "skinparam hyperlinkColor #252327",
            "skinparam hyperlinkUnderline false",
            # A swimlane is exactly as wide as its widest unwrapped label, so without this a diagram
            # grows sideways with every added lane and every sentence-long step, and a three-lane
            # activity renders as a landscape strip nobody can read. Wrapping trades width for
            # height, which a page has more of. Measured on a two-lane, thirteen-step diagram:
            # 2247x804 unwrapped against 1304x965 at 180 — 42% narrower.
            *label_wrap_skinparams(self._config),
            f"title {puml_text(name)}",
            "",
        ]
        if initial_lane_id and initial_lane_id in lane_map:
            lane = lane_map[initial_lane_id]
            lines.append(f"|{puml_text(str(lane.get('label') or lane['id']))}|")
        lines.append("start")
        lines.append("")
        lines.extend(body_lines)
        lines.append("")
        lines.append("stop")
        lines.append("@enduml")

        body = "\n".join(lines)
        threshold = configured_puml_size_warning_threshold(self._config)
        warn_when_puml_exceeds_threshold(body, threshold=threshold)
        return body

    def inject_includes(self, body: str, repo_root: Path) -> str:
        del repo_root
        return body

    def collect_references(
        self,
        diagram_type: str,
        repo_root: Path,
        *,
        diagram_entities: Mapping[str, object] | None = None,
        diagram_connections: list[dict[str, object]] | None = None,
        bindings: list[dict[str, object]] | None = None,
    ) -> DiagramRendererReferences:
        del diagram_type, repo_root, diagram_entities, diagram_connections
        entity_ids: list[str] = []
        conn_ids: list[str] = []
        for b in (bindings or []):
            if not isinstance(b, dict):
                continue
            target = b.get("target")
            if not isinstance(target, dict):
                continue
            eid = target.get("entity_id")
            cid = target.get("connection_id")
            if eid and str(eid) not in entity_ids:
                entity_ids.append(str(eid))
            if cid and str(cid) not in conn_ids:
                conn_ids.append(str(cid))
        return DiagramRendererReferences(entity_ids=tuple(entity_ids), connection_ids=tuple(conn_ids))


# ── Index builders ────────────────────────────────────────────────────────────


def _build_step_by_id(kd: Mapping[str, object]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for key in _STEP_KEYS:
        raw = kd.get(key)
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and item.get("id"):
                    result[str(item["id"])] = {**item, "type": item.get("type") or key}
    return result


def _build_single_target(kcs: list[dict[str, object]], conn_type: str) -> dict[str, str]:
    return {
        str(kc["source"]): str(kc["target"])
        for kc in kcs
        if isinstance(kc, dict) and kc.get("conn_type") == conn_type
        and kc.get("source") and kc.get("target")
    }


def _build_multi_target(kcs: list[dict[str, object]], conn_type: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for kc in kcs:
        if isinstance(kc, dict) and kc.get("conn_type") == conn_type and kc.get("source") and kc.get("target"):
            result.setdefault(str(kc["source"]), []).append(str(kc["target"]))
    return result


def _build_notes_index(
    kd: Mapping[str, object], kcs: list[dict[str, object]]
) -> dict[str, dict[str, Any]]:
    raw_notes = kd.get("note")
    if not isinstance(raw_notes, list) or not raw_notes:
        return {}
    note_by_id = {str(n["id"]): n for n in raw_notes if isinstance(n, dict) and n.get("id")}
    return {
        str(kc["target"]): note_by_id[str(kc["source"])]
        for kc in kcs
        if isinstance(kc, dict) and kc.get("conn_type") == "step-note-of"
        and str(kc.get("source") or "") in note_by_id and kc.get("target")
    }


def _branch_owned_set(graph: StepGraph) -> set[str]:
    owned = _branch_entries(graph)
    changed = True
    while changed:
        changed = False
        for src, tgt in graph.flow_next.items():
            if src in owned and tgt not in owned:
                owned.add(tgt)
                changed = True
    return owned


def _find_root(graph: StepGraph, branch_owned: set[str]) -> str | None:
    """Where the walk starts: a step nothing flows into and no branch owns.

    A back edge leaves no such step — every step of a retry loop is reached from somewhere — and
    returning None then drew `start` and `stop` with nothing between them. So a graph that loops
    falls back to a step no branch enters, and failing that to the first declared step: an entry
    into a cycle is a choice rather than a fact, and any of them draws the whole loop.
    """
    has_incoming_flow = set(graph.flow_next.values())
    for step_id in graph.step_by_id:
        if step_id not in branch_owned and step_id not in has_incoming_flow:
            return step_id
    branch_entries = _branch_entries(graph)
    for step_id in graph.step_by_id:
        if step_id not in branch_entries:
            return step_id
    return next(iter(graph.step_by_id), None)


def _branch_entries(graph: StepGraph) -> set[str]:
    entries = (
        set(graph.then_target.values())
        | set(graph.else_target.values())
        | set(graph.contains_first.values())
    )
    for ids in graph.fork_branches.values():
        entries.update(ids)
    return entries


def _read_lanes(kd: Mapping[str, object]) -> list[dict[str, Any]]:
    raw = kd.get("swimlane")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict) and item.get("id")]

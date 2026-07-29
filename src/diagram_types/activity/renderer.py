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
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.ontology_representation.ontology_protocol import DiagramRendererReferences
from src.infrastructure.rendering.puml_safety import (
    configured_puml_size_warning_threshold,
    warn_when_puml_exceeds_threshold,
)

from ._step_links import link_suffix, sentinel_wrapped, user_link_suffix

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
        del diagram_type, entities, connections
        diagram_name = re.sub(r"[^a-zA-Z0-9_-]", "-", name.lower()).strip("-") or "activity"
        kd = diagram_entities or {}
        kcs = diagram_connections or []

        step_by_id = _build_step_by_id(kd)
        flow_next = _build_single_target(kcs, "step-flow")
        then_target = _build_single_target(kcs, "step-then")
        else_target = _build_single_target(kcs, "step-else")
        fork_branches = _build_multi_target(kcs, "step-fork-branch")
        contains_first = _build_single_target(kcs, "step-contains")
        notes_index = _build_notes_index(kd, kcs)
        lane_index = _build_lane_index(kcs)

        branch_owned = _branch_owned_set(then_target, else_target, fork_branches, contains_first, flow_next)

        lanes = _read_lanes(kd)
        lane_map = {lane["id"]: lane for lane in lanes}
        has_lanes = bool(lanes)

        root_id = _find_root(step_by_id, flow_next, branch_owned)
        initial_lane_id = lane_index.get(root_id) if root_id else None
        if initial_lane_id is None and lanes:
            initial_lane_id = lanes[0]["id"]

        lines: list[str] = [
            f"@startuml {diagram_name}",
            # Sentinel arch:// links wrap the step labels themselves (see _step_links) —
            # style hyperlinks as plain text so the anchor is invisible, not blue/underlined.
            "skinparam hyperlinkColor #252327",
            "skinparam hyperlinkUnderline false",
            f"title {_puml_text(name)}",
            "",
        ]
        if initial_lane_id and initial_lane_id in lane_map:
            lane = lane_map[initial_lane_id]
            lines.append(f"|{_puml_text(str(lane.get('label') or lane['id']))}|")
        lines.append("start")
        lines.append("")

        state: dict[str, str | None] = {"current_lane": initial_lane_id}
        visited: set[str] = set()
        ctx = (step_by_id, flow_next, then_target, else_target, fork_branches, contains_first,
               notes_index, lane_index, lane_map, has_lanes, state)
        if root_id:
            _emit_from(root_id, ctx, lines, visited)
        else:
            _emit_orphans(kd, branch_owned, ctx, lines, visited)

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


# ── Context type alias ────────────────────────────────────────────────────────
# (step_by_id, flow_next, then_target, else_target, fork_branches,
#  contains_first, notes_index, lane_index, lane_map, has_lanes, state)
_Ctx = tuple[
    dict[str, dict[str, Any]],
    dict[str, str],
    dict[str, str],
    dict[str, str],
    dict[str, list[str]],
    dict[str, str],
    dict[str, dict[str, Any]],
    dict[str, str],
    dict[str, dict[str, Any]],
    bool,
    dict[str, str | None],
]


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


def _build_lane_index(kcs: list[dict[str, object]]) -> dict[str, str]:
    return _build_single_target(kcs, "step-in-lane")


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


def _branch_owned_set(
    then_target: dict[str, str],
    else_target: dict[str, str],
    fork_branches: dict[str, list[str]],
    contains_first: dict[str, str],
    flow_next: dict[str, str],
) -> set[str]:
    entries: set[str] = set(then_target.values()) | set(else_target.values()) | set(contains_first.values())
    for ids in fork_branches.values():
        entries.update(ids)
    owned = set(entries)
    changed = True
    while changed:
        changed = False
        for src, tgt in flow_next.items():
            if src in owned and tgt not in owned:
                owned.add(tgt)
                changed = True
    return owned


def _find_root(
    step_by_id: dict[str, dict[str, Any]],
    flow_next: dict[str, str],
    branch_owned: set[str],
) -> str | None:
    has_incoming_flow = set(flow_next.values())
    for step_id in step_by_id:
        if step_id not in branch_owned and step_id not in has_incoming_flow:
            return step_id
    return None


# ── Emission ──────────────────────────────────────────────────────────────────


def _emit_from(start_id: str, ctx: _Ctx, lines: list[str], visited: set[str]) -> None:
    step_id: str | None = start_id
    while step_id and step_id not in visited:
        step = ctx[0].get(step_id)
        if not step:
            break
        visited.add(step_id)
        _emit_step(step, step_id, ctx, lines, visited)
        step_id = ctx[1].get(step_id)


def _emit_orphans(
    kd: Mapping[str, object],
    branch_owned: set[str],
    ctx: _Ctx,
    lines: list[str],
    visited: set[str],
) -> None:
    for key in _STEP_KEYS:
        raw = kd.get(key)
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and item.get("id"):
                    sid = str(item["id"])
                    if sid not in branch_owned and sid not in visited:
                        _emit_from(sid, ctx, lines, visited)


def _emit_step(step: dict[str, Any], step_id: str, ctx: _Ctx, lines: list[str], visited: set[str]) -> None:
    (step_by_id, flow_next, then_target, else_target, fork_branches,
     contains_first, notes_index, lane_index, lane_map, has_lanes, state) = ctx
    stype = str(step.get("type") or "")

    if stype == "action":
        _maybe_switch_lane(step_id, lane_index, lane_map, state, lines, has_lanes=has_lanes)
        label = _puml_text(str(step.get("label") or "action"))
        lines.append(f":{sentinel_wrapped(step, label)}{user_link_suffix(step)};")
        _emit_step_note(step_id, notes_index, lines)

    elif stype == "decision":
        _maybe_switch_lane(step_id, lane_index, lane_map, state, lines, has_lanes=has_lanes)
        condition = _puml_text(str(step.get("condition") or "?"))
        then_label = _puml_text(str(step.get("then_label") or "yes"))
        else_label = _puml_text(str(step.get("else_label") or "no"))
        lines.append(f"if ({sentinel_wrapped(step, f'{condition}?')}{user_link_suffix(step)}) then ({then_label})")
        _emit_step_note(step_id, notes_index, lines)
        then_first = then_target.get(step_id)
        if then_first:
            _emit_from(then_first, ctx, lines, visited)
        lines.append(f"else ({else_label})")
        else_first = else_target.get(step_id)
        if else_first:
            _emit_from(else_first, ctx, lines, visited)
        lines.append("endif")

    elif stype == "fork":
        # No sentinel link here: PlantUML's `fork` keyword takes no label/link argument at
        # all (`fork [[url]]` is a syntax error) and renders as an unlabeled, ungrouped bar
        # with no distinguishing SVG attribute — forks are not selectable in the viewer.
        _maybe_switch_lane(step_id, lane_index, lane_map, state, lines, has_lanes=has_lanes)
        branches = fork_branches.get(step_id, [])
        if branches:
            lines.append("fork")
            _emit_step_note(step_id, notes_index, lines)
            for i, branch_start in enumerate(branches):
                if i > 0:
                    lines.append("fork again")
                _emit_from(branch_start, ctx, lines, set(visited))
            lines.append("end fork")

    elif stype == "partition":
        label = _puml_text(str(step.get("label") or "Partition"))
        lines.append(f'partition "{label}"{link_suffix(step)} {{')
        _emit_step_note(step_id, notes_index, lines)
        contains_id = contains_first.get(step_id)
        if contains_id:
            _emit_from(contains_id, ctx, lines, visited)
        lines.append("}")


def _maybe_switch_lane(
    step_id: str,
    lane_index: dict[str, str],
    lane_map: dict[str, dict[str, Any]],
    state: dict[str, str | None],
    lines: list[str],
    *,
    has_lanes: bool,
) -> None:
    lane_id = lane_index.get(step_id)
    if not lane_id:
        if has_lanes and step_id:
            lines.append(f"' WARNING: step '{step_id}' has no step-in-lane connection")
        return
    if lane_id == state["current_lane"]:
        return
    lane = lane_map.get(lane_id)
    if lane:
        lines.append(f"|{_puml_text(str(lane.get('label') or lane['id']))}|")
        state["current_lane"] = lane_id


def _emit_step_note(step_id: str, notes_index: dict[str, dict[str, Any]], lines: list[str]) -> None:
    note = notes_index.get(step_id)
    if not note:
        return
    side = str(note.get("side") or "right")
    if side not in ("left", "right"):
        side = "right"
    text = str(note.get("text") or "")
    if not text:
        return
    if "\n" in text:
        lines.append(f"note {side}")
        for note_line in text.split("\n"):
            lines.append(_puml_text(note_line))
        lines.append("end note")
    else:
        lines.append(f"note {side}: {_puml_text(text)}")


def _read_lanes(kd: Mapping[str, object]) -> list[dict[str, Any]]:
    raw = kd.get("swimlane")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict) and item.get("id")]


def _puml_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", " ").replace("|", "/")

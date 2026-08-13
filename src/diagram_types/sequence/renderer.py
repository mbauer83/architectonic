"""Sequence diagram PUML renderer — PlantUML sequence syntax (v2 schema).

diagram_entities keys:
  lifeline:  [{id, label?, participant_type?}]           # array order = left-to-right
  message:   [{id, label?, arrow?, activate_target?, deactivate_target?}]  # array order = sequence
  grouping:  [{id, kind, label?, operands: [{guard?, start_message_id, end_message_id}]}]
  note:      [{id, text, placement?, lifeline_ids: [...], after_message_id?}]

Connections in diagram_entities._connections (or diagram_connections parameter):
  seq-from:  message → lifeline  (source)
  seq-to:    message → lifeline  (target)
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.ontology_representation.ontology_protocol import DiagramRendererReferences
from src.infrastructure.rendering.puml_label_wrapping import label_wrap_skinparams

_PARTICIPANT_KEYWORD: dict[str, str] = {
    "participant": "participant",
    "actor": "actor",
    "boundary": "boundary",
    "control": "control",
    "entity": "entity",
    "database": "database",
    "queue": "queue",
}

_ARROW_MAP: dict[str, str] = {
    "sync": "->",
    "async": "->>",
    "reply": "-->",
    "self": "->",
    "create": "->",
    "destroy": "-\\\\",
    "": "->",
}


class SequencePumlRenderer:
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
        diagram_name = re.sub(r"[^a-zA-Z0-9_-]", "-", name.lower()).strip("-") or "sequence"
        kd = diagram_entities or {}

        # Prefer explicit diagram_connections; fall back to _connections in diagram_entities
        kcs: list[dict[str, object]] = diagram_connections or []
        if not kcs:
            raw = kd.get("_connections")
            if isinstance(raw, list):
                kcs = [c for c in raw if isinstance(c, dict)]

        lifelines = _read_list(kd, "lifeline")
        messages = _read_list(kd, "message")  # array order = sequence
        groupings = _read_list(kd, "grouping")
        notes = _read_list(kd, "note")

        alias_map = _build_alias_map(lifelines, repo_root)
        from_map = _build_single(kcs, "seq-from")
        to_map = _build_single(kcs, "seq-to")
        msg_id_to_idx = {str(m["id"]): i for i, m in enumerate(messages)}

        lines: list[str] = [
            f"@startuml {diagram_name}",
            *label_wrap_skinparams(self._config),
            f"title {_puml_text(name)}",
            "",
        ]

        for ll in lifelines:
            ll_id = str(ll.get("id") or "")
            alias = alias_map.get(ll_id, ll_id)
            label = str(ll.get("label") or ll_id)
            ptype = str(ll.get("participant_type") or "participant")
            keyword = _PARTICIPANT_KEYWORD.get(ptype, "participant")
            lines.append(f'{keyword} "{_puml_text(label)}" as {alias}')

        if lifelines:
            lines.append("")

        _emit_messages_with_groupings(
            messages, groupings, notes, from_map, to_map, alias_map, msg_id_to_idx, lines
        )

        lines.append("")
        lines.append("@enduml")
        return "\n".join(lines)

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
            if eid and str(eid) not in entity_ids:
                entity_ids.append(str(eid))
            cid = target.get("connection_id")
            if cid and str(cid) not in conn_ids:
                conn_ids.append(str(cid))
            for cid2 in (target.get("connection_ids") or []):
                if cid2 and str(cid2) not in conn_ids:
                    conn_ids.append(str(cid2))
        return DiagramRendererReferences(entity_ids=tuple(entity_ids), connection_ids=tuple(conn_ids))


# ── Helpers ───────────────────────────────────────────────────────────────────


def _normalize_puml_alias(alias: str) -> str:
    """Diagram-types may not import ``application`` (dependency policy); mirrors
    ``application.artifact_parsing.normalize_puml_alias`` — same duplication the C4
    renderer already carries as ``c4._c4_types._normalize_alias``."""
    return alias.strip().replace("-", "_")


def _read_list(kd: Mapping[str, object], key: str) -> list[dict[str, Any]]:
    raw = kd.get(key)
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict) and item.get("id")]


def _build_alias_map(lifelines: list[dict[str, Any]], repo_root: Path) -> dict[str, str]:
    """Alias every lifeline by a normalized, stable identity — never a positional ``LL{n}``.

    A bound lifeline's PUML alias must match what ``_diagram_context.py`` publishes as the
    entity's ``source_alias``/``target_alias`` (both derive from
    ``_normalize_puml_alias(entity.display_alias)``); an unbound lifeline's alias must match
    the ``display_alias`` the diagram-local entity extraction gives it, which is its own local
    id (``_diagram_entity_extraction.extract_diagram_entities``). Either way the frontend
    viewer extension resolves clicks/highlights against the diagram context's entity list — a
    positional alias has no counterpart there and could never be matched.
    """
    from src.infrastructure.artifact_index import shared_artifact_index  # noqa: PLC0415

    query = None
    alias_map: dict[str, str] = {}
    for ll in lifelines:
        ll_id = ll.get("id")
        if not ll_id:
            continue
        alias = _normalize_puml_alias(str(ll_id))
        entity_id = ll.get("entity_id")
        if entity_id:
            if query is None:
                query = shared_artifact_index([repo_root])
            entity = query.get_entity(str(entity_id))
            if entity is not None and entity.display_alias:
                alias = _normalize_puml_alias(entity.display_alias)
        alias_map[ll_id] = alias
    return alias_map


def _build_single(kcs: list[dict[str, object]], conn_type: str) -> dict[str, str]:
    return {
        str(kc["source"]): str(kc["target"])
        for kc in kcs
        if isinstance(kc, dict)
        and kc.get("conn_type") == conn_type
        and kc.get("source") and kc.get("target")
    }


def _read_operands(g: dict[str, Any]) -> list[dict[str, Any]]:
    ops = g.get("operands")
    if not isinstance(ops, list):
        return []
    return [op for op in ops if isinstance(op, dict)]


def _emit_messages_with_groupings(
    messages: list[dict[str, Any]],
    groupings: list[dict[str, Any]],
    notes: list[dict[str, Any]],
    from_map: dict[str, str],
    to_map: dict[str, str],
    alias_map: dict[str, str],
    msg_id_to_idx: dict[str, int],
    lines: list[str],
) -> None:
    notes_after: dict[str, list[dict[str, Any]]] = {}
    notes_at_end: list[dict[str, Any]] = []
    for note in notes:
        after_id = str(note.get("after_message_id") or "")
        if after_id and after_id in msg_id_to_idx:
            notes_after.setdefault(after_id, []).append(note)
        else:
            notes_at_end.append(note)

    # open_at[idx] = [(grouping, span)], close_at[idx] = [(grouping, span)]
    # else_at[idx] = [(grouping, op_idx, guard, span)]
    open_at: dict[int, list[tuple[dict[str, Any], int]]] = {}
    close_at: dict[int, list[tuple[dict[str, Any], int]]] = {}
    else_at: dict[int, list[tuple[dict[str, Any], int, str, int]]] = {}

    for g in groupings:
        ops = _read_operands(g)
        if not ops:
            continue
        s_idx = msg_id_to_idx.get(str(ops[0].get("start_message_id") or ""))
        e_idx = msg_id_to_idx.get(str(ops[-1].get("end_message_id") or ""))
        if s_idx is None or e_idx is None:
            continue
        span = e_idx - s_idx
        open_at.setdefault(s_idx, []).append((g, span))
        close_at.setdefault(e_idx, []).append((g, span))
        for i, op in enumerate(ops[1:], 1):
            op_s = msg_id_to_idx.get(str(op.get("start_message_id") or ""))
            if op_s is not None:
                guard = str(op.get("guard") or "")
                else_at.setdefault(op_s, []).append((g, i, guard, span))

    for idx, msg in enumerate(messages):
        msg_id = str(msg.get("id") or "")

        # Else boundaries: innermost first (smallest span)
        for _g, _i, guard, _span in sorted(else_at.get(idx, []), key=lambda x: x[3]):
            lines.append(f"else {_puml_text(guard)}" if guard else "else")

        # Open groupings: outermost first (largest span)
        for g, _span in sorted(open_at.get(idx, []), key=lambda x: -x[1]):
            _emit_grouping_open(g, lines)

        _emit_message(msg, from_map, to_map, alias_map, lines)

        for note in notes_after.get(msg_id, []):
            _emit_note(note, alias_map, lines)

        # Close groupings: innermost first (smallest span)
        for _g, _span in sorted(close_at.get(idx, []), key=lambda x: x[1]):
            lines.append("end")

    for note in notes_at_end:
        _emit_note(note, alias_map, lines)


def _emit_grouping_open(g: dict[str, Any], lines: list[str]) -> None:
    """Open one grouping. **A guard is emitted bare**, never in brackets.

    PlantUML draws the brackets itself, and a single `[...]` in its source is *link* syntax —
    `[target label]` — so `alt [features computed]` rendered as a hyperlink whose target was the
    first token and whose label was the rest: the word "features" disappeared from the image.
    Measured against the bundled plantuml.jar, `alt [features computed]` draws `computed` and
    `alt features computed` draws `[features computed]`.

    Single-word guards round-trip either way, which is why this survived: they are the common case.
    """
    kind = str(g.get("kind") or "opt")
    label = str(g.get("label") or "")
    ops = _read_operands(g)
    first_guard = str(ops[0].get("guard") or "") if ops else ""

    if kind == "group" and label:
        lines.append(f"group {_puml_text(label)}")
    elif kind in ("loop", "break", "critical") and label:
        lines.append(f"{kind} {_puml_text(label)}")
    elif first_guard:
        lines.append(f"{kind} {_puml_text(first_guard)}")
    else:
        lines.append(kind)


def _emit_message(
    msg: dict[str, Any],
    from_map: dict[str, str],
    to_map: dict[str, str],
    alias_map: dict[str, str],
    lines: list[str],
) -> None:
    msg_id = str(msg.get("id") or "")
    src_ll = from_map.get(msg_id, "")
    tgt_ll = to_map.get(msg_id, "")
    src_alias = alias_map.get(src_ll, src_ll)
    tgt_alias = alias_map.get(tgt_ll, tgt_ll)
    arrow_key = str(msg.get("arrow") or "sync")
    arrow = _ARROW_MAP.get(arrow_key, "->")
    label = _puml_text(str(msg.get("label") or ""))
    activate = bool(msg.get("activate_target"))
    deactivate = bool(msg.get("deactivate_target"))

    if arrow_key == "self" or (src_ll and src_ll == tgt_ll):
        if src_alias:
            lines.append(f"{src_alias} {arrow} {src_alias}: {label}")
        return

    if not (src_alias and tgt_alias):
        if label:
            lines.append(f"' {label}")
        return

    if arrow_key == "create":
        lines.append(f"{src_alias} {arrow} {tgt_alias} **: {label}")
    elif arrow_key == "destroy":
        lines.append(f"{src_alias} {arrow} {tgt_alias} !!: {label}")
    elif activate:
        lines.append(f"{src_alias} {arrow} {tgt_alias} ++: {label}")
    elif deactivate:
        lines.append(f"{src_alias} {arrow} {tgt_alias} --: {label}")
    else:
        lines.append(f"{src_alias} {arrow} {tgt_alias}: {label}")


def _emit_note(note: dict[str, Any], alias_map: dict[str, str], lines: list[str]) -> None:
    placement = str(note.get("placement") or "right_of")
    lifeline_ids = note.get("lifeline_ids")
    if not isinstance(lifeline_ids, list):
        lifeline_ids = []
    text = str(note.get("text") or "")
    if not text:
        return
    aliases = [alias_map.get(str(lid), str(lid)) for lid in lifeline_ids if lid]
    if not aliases:
        return
    if placement == "left_of":
        lines.append(f"note left of {aliases[0]}: {_puml_text(text)}")
    elif placement == "over":
        lines.append(f"note over {', '.join(aliases)}: {_puml_text(text)}")
    else:
        lines.append(f"note right of {aliases[0]}: {_puml_text(text)}")


def _puml_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", " ").replace("|", "/")

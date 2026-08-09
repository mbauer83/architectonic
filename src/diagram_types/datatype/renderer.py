"""Datatype diagram PUML renderer — restricted UML class diagram (no operations).

diagram_entities keys:
  classifier: [{id, label?, classifier_kind?, attributes?: [...], literals?: [...],
                is_abstract?: bool, identity?: [attr_id...],
                unique_keys?: [{name?, attribute_ids: [attr_id...]}]}]
  generalization_set: [{id, label?, is_covering?: bool, is_disjoint?: bool}]

diagram_connections (all with conn_type from the dt-* vocabulary):
  dt-association   — solid line (symmetric)
  dt-aggregation   — hollow diamond at source (whole → part, shared)
  dt-composition   — filled diamond at source (whole → part, exclusive)
  dt-generalization — hollow triangle at target (child → parent)
  dt-dependency    — dashed arrow (source uses/depends-on target)

  Each connection dict: {source, target, conn_type, src_multiplicity?,
                         tgt_multiplicity?, label?}
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.ontology_representation.ontology_protocol import DiagramRendererReferences
from src.infrastructure.rendering.puml_label_wrapping import label_wrap_skinparams

_ALIAS_RE = re.compile(r"[^A-Za-z0-9_]")
_NEWLINE_RE = re.compile(r"\r?\n|\r")

# dt-* conn_type → PlantUML arrow string
_PUML_ARROWS: dict[str, str] = {
    "dt-association": "--",
    "dt-aggregation": "o--",
    "dt-composition": "*--",
    "dt-generalization": "--|>",
    "dt-dependency": "..>",
}

# classifier_kind → (puml keyword, stereotype label or None)
_KIND_META: dict[str, tuple[str, str | None]] = {
    "class": ("class", None),
    "datatype": ("class", "datatype"),
    "enumeration": ("enum", None),
    "primitive": ("class", "primitive"),
}


def _safe_alias(raw_id: str) -> str:
    return "_" + _ALIAS_RE.sub("_", raw_id)


def _safe_text(text: str) -> str:
    return _NEWLINE_RE.sub(" ", text)


def _keyword(kind: str, is_abstract: bool) -> str:
    keyword, _ = _KIND_META.get(kind, ("class", None))
    return f"abstract {keyword}" if is_abstract and keyword == "class" else keyword


def _key_markers(c: dict[str, Any]) -> dict[str, list[str]]:
    """Map attribute id → PUML key markers ({id}, {unique}, {unique:name})."""
    markers: dict[str, list[str]] = {}
    for attr_id in (c.get("identity") or []):
        markers.setdefault(str(attr_id), []).append("{id}")
    for key in (c.get("unique_keys") or []):
        if not isinstance(key, dict):
            continue
        name = str(key.get("name") or "").strip()
        marker = f"{{unique:{name}}}" if name else "{unique}"
        for attr_id in (key.get("attribute_ids") or []):
            markers.setdefault(str(attr_id), []).append(marker)
    return markers


def _render_attr(attr: dict[str, Any], markers: dict[str, list[str]]) -> str:
    name = str(attr.get("name") or "")
    parts: list[str] = [f"  + {name}"]
    atype = str(attr.get("type") or "")
    if atype:
        parts.append(f" : {atype}")
    mult = str(attr.get("multiplicity") or "")
    if mult:
        parts.append(f" [{mult}]")
    if attr.get("optional"):
        parts.append(" {optional}")
    parts.extend(f" {marker}" for marker in markers.get(str(attr.get("id") or ""), []))
    return "".join(parts)


def _key_note_lines(c: dict[str, Any], alias: str) -> list[str]:
    """A composite-key note resolving attribute ids → names for readability."""
    id_to_name = {
        str(a.get("id") or ""): str(a.get("name") or "")
        for a in (c.get("attributes") or [])
        if isinstance(a, dict)
    }
    def names(ids: Any) -> str:
        return ", ".join(id_to_name.get(str(i), str(i)) for i in ids)

    body: list[str] = []
    identity: list[Any] = c.get("identity") or []
    if len(identity) > 1:
        body.append(f"«identity» ({names(identity)})")
    for key in (c.get("unique_keys") or []):
        if isinstance(key, dict) and (key.get("attribute_ids") or []):
            label = str(key.get("name") or "").strip()
            head = f"«unique {label}»" if label else "«unique»"
            body.append(f"{head} ({names(key['attribute_ids'])})")
    return [f"note right of {alias}", *body, "end note"] if body else []


def _render_classifier(c: dict[str, Any]) -> list[str]:
    eid = str(c.get("id") or "")
    label = _safe_text(str(c.get("label") or eid))
    kind = str(c.get("classifier_kind") or "class")
    alias = _safe_alias(eid)
    _, stereotype = _KIND_META.get(kind, ("class", None))

    # PlantUML class syntax requires the stereotype AFTER the alias:
    #   class "Label" as Alias <<stereotype>> { … }
    head_parts = [_keyword(kind, bool(c.get("is_abstract"))), f'"{label}"', f"as {alias}"]
    if stereotype:
        head_parts.append(f"<<{stereotype}>>")
    lines: list[str] = [" ".join(head_parts) + " {"]

    if kind == "enumeration":
        lines.extend(f"  {_safe_text(str(lit))}" for lit in (c.get("literals") or []))
    else:
        markers = _key_markers(c)
        lines.extend(
            _render_attr(attr, markers)
            for attr in (c.get("attributes") or [])
            if isinstance(attr, dict)
        )

    lines.append("}")
    lines.extend(_key_note_lines(c, alias))
    note = _safe_text(str(c.get("note") or "")).strip()
    if note:
        lines.extend((f"note right of {alias}", note, "end note"))
    return lines


def _gen_set_constraint(gset: dict[str, Any]) -> str:
    covering = "complete" if gset.get("is_covering") else "incomplete"
    disjoint = "disjoint" if gset.get("is_disjoint") else "overlapping"
    return f"{{{covering}, {disjoint}}}"


def _render_generalization_sets(
    gen_sets: list[dict[str, Any]],
    connections: list[dict[str, Any]],
) -> list[str]:
    """Render a constraint note per generalization_set referenced by ≥1 dt-generalization.

    The note is attached to the general (target) classifier of the set's generalizations.
    """
    sets_by_id = {str(s.get("id") or ""): s for s in gen_sets if isinstance(s, dict)}
    general_end: dict[str, str] = {}
    for conn in connections:
        if str(conn.get("conn_type") or "") != "dt-generalization":
            continue
        set_id = str(conn.get("generalization_set") or "")
        if set_id and set_id in sets_by_id and set_id not in general_end:
            general_end[set_id] = str(conn.get("target") or "")

    lines: list[str] = []
    for set_id, target in general_end.items():
        if not target:
            continue
        gset = sets_by_id[set_id]
        label = _safe_text(str(gset.get("label") or set_id))
        note = _safe_text(str(gset.get("note") or "")).strip()
        lines.extend((
            f"note bottom of {_safe_alias(target)}",
            f"GeneralizationSet «{label}» {_gen_set_constraint(gset)}",
            *([note] if note else []),
            "end note",
        ))
    return lines


def _render_connection(kc: dict[str, Any]) -> list[str]:
    src = _safe_alias(str(kc.get("source") or ""))
    tgt = _safe_alias(str(kc.get("target") or ""))
    conn_type = str(kc.get("conn_type") or "dt-association")
    arrow = _PUML_ARROWS.get(conn_type, "--")
    src_card = str(kc.get("src_multiplicity") or "")
    tgt_card = str(kc.get("tgt_multiplicity") or "")
    label = _safe_text(str(kc.get("label") or ""))

    src_part = f' "{src_card}"' if src_card else ""
    tgt_part = f'"{tgt_card}" ' if tgt_card else ""
    label_part = f" : {label}" if label else ""

    lines = [f"{src}{src_part} {arrow} {tgt_part}{tgt}{label_part}"]
    note = _safe_text(str(kc.get("note") or "")).strip()
    if note:
        lines.extend(("note on link", note, "end note"))
    return lines


class DatatypePumlRenderer:
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
        del entities, connections, diagram_type, repo_root
        kd = diagram_entities or {}
        raw_cls = kd.get("classifier")
        classifiers: list[dict[str, Any]] = [
            c for c in (raw_cls if isinstance(raw_cls, (list, tuple)) else [])
            if isinstance(c, dict)
        ]
        kcs: list[dict[str, Any]] = [
            kc for kc in (diagram_connections or []) if isinstance(kc, dict)
        ]
        raw_gs = kd.get("generalization_set")
        gen_sets: list[dict[str, Any]] = [
            g for g in (raw_gs if isinstance(raw_gs, (list, tuple)) else [])
            if isinstance(g, dict)
        ]

        lines: list[str] = [
            f"@startuml {_safe_text(name)}",
            "skinparam linetype ortho",
            *label_wrap_skinparams(self._config),
            "",
        ]
        for c in classifiers:
            lines.extend(_render_classifier(c))
            lines.append("")
        for kc in kcs:
            if kc.get("conn_type") in _PUML_ARROWS:
                lines.extend(_render_connection(kc))
        lines.extend(_render_generalization_sets(gen_sets, kcs))
        lines += ["", "@enduml"]
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
        for b in bindings or []:
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
        return DiagramRendererReferences(
            entity_ids=tuple(entity_ids),
            connection_ids=tuple(conn_ids),
        )

"""PlantUML renderer for C4-style diagram-owned diagram types.

Uses the C4-PlantUML stdlib (``!include <C4/C4_Component>``) for standard shaped
elements (Person glyph, cylinder for databases, queue shape for message brokers).
Shape resolution: explicit ``shape`` attr → technology-inferred variant → item-type default.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.diagram_types.c4._resolve import _ResolvedItem, resolve_c4_state
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.ontology_representation.ontology_protocol import DiagramRendererReferences
from src.infrastructure.rendering.puml_label_wrapping import label_wrap_skinparams
from src.infrastructure.rendering.puml_safety import (
    configured_puml_size_warning_threshold,
    warn_when_puml_exceeds_threshold,
)

# Technology substring → shape variant ("db" | "queue" | "generic")
_DB_TECHS = ("database", "sql", "postgres", "mysql", "oracle", "mariadb", "sqlite",
              "mongodb", "redis", "cassandra", "rdbms")
_QUEUE_TECHS = ("queue", "kafka", "rabbitmq", "sqs", "activemq", "nats",
                 "bus", "broker", "pubsub")


def _tech_variant(technology: str) -> str:
    t = technology.lower()
    for kw in _DB_TECHS:
        if kw in t:
            return "db"
    for kw in _QUEUE_TECHS:
        if kw in t:
            return "queue"
    return "generic"


def _c4_macro_name(item_type: str, variant: str, external: bool) -> str:
    ext = "_Ext" if external else ""
    if item_type == "person":
        return f"Person{ext}"
    if item_type == "software-system":
        return f"SystemDb{ext}" if variant == "db" else f"System{ext}"
    if item_type == "container":
        if variant == "db":
            return f"ContainerDb{ext}"
        if variant == "queue":
            return f"ContainerQueue{ext}"
        return f"Container{ext}"
    if item_type == "component":
        if variant == "db":
            return f"ComponentDb{ext}"
        if variant == "queue":
            return f"ComponentQueue{ext}"
        return f"Component{ext}"
    return f"Container{ext}"  # unknown item type → generic container shape


class C4PumlRenderer:
    def __init__(
        self,
        config: Mapping[str, Any],
        *,
        person_archimate_types: frozenset[str] = frozenset(),
    ) -> None:
        self._config = dict(config)
        self._person_archimate_types = person_archimate_types

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
        edge_labels: dict[str, str] | None = None,
    ) -> str:
        del entities, connections
        diagram_name = re.sub(r"[^a-zA-Z0-9_-]", "-", name.lower()).strip("-") or "c4-diagram"
        state = resolve_c4_state(
            self._config, diagram_type, repo_root,
            diagram_entities or {}, diagram_connections or [],
            self._person_archimate_types,
        )
        lines: list[str] = [
            f"@startuml {diagram_name}",
            "!include <C4/C4_Component>",
            "left to right direction",
            "skinparam shadowing false",
            "skinparam linetype ortho",
            "skinparam defaultTextAlignment center",
            *label_wrap_skinparams(self._config),
            "",
            f"title {name}",
            "",
        ]

        show_desc = bool((self._config.get("c4") or {}).get("show_node_descriptions", False))

        if state.scope_render_mode == "node":
            lines.append(self._render_item(state.scope_item, show_descriptions=show_desc))
        else:
            lines.append(
                f'System_Boundary({state.scope_item.alias}, "{_escape_puml(state.scope_item.label)}") {{'
            )
            for item in state.internal_items:
                lines.append(f"  {self._render_item(item, show_descriptions=show_desc)}")
            self._append_hidden_chain(lines, [item.alias for item in state.internal_items], indent="  ")
            lines.append("}")

        self._append_hidden_chain(lines, [state.scope_item.alias], indent="")

        outside_items = state.outside_items
        if outside_items:
            for item in outside_items:
                lines.append(self._render_item(item, show_descriptions=show_desc))
            lines.append("")
            ordered_aliases = (
                [item.alias for item in outside_items if item.item_type == "person"]
                + [state.scope_item.alias]
                + [item.alias for item in outside_items if item.item_type != "person"]
            )
            self._append_hidden_chain(lines, ordered_aliases, indent="")

        lines.append("")
        for conn in state.connections:
            raw_label = (
                edge_labels.get(f"{conn.src_alias}:{conn.tgt_alias}", conn.label)
                if edge_labels
                else conn.label
            )
            label = _escape_puml(raw_label) if raw_label else ""
            lines.append(f"{conn.src_alias} --> {conn.tgt_alias} : {label}")
        lines.append("@enduml")

        body = "\n".join(line for line in lines if line is not None)
        threshold = configured_puml_size_warning_threshold(self._config)
        warn_when_puml_exceeds_threshold(body, threshold=threshold)
        return body + "\n"

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
        state = resolve_c4_state(
            self._config, diagram_type, repo_root,
            diagram_entities or {}, diagram_connections or [],
            self._person_archimate_types,
        )
        entity_ids: list[str] = list(state.entity_ids)
        conn_ids: list[str] = list(state.connection_artifact_ids)
        for b in (bindings or []):
            if not isinstance(b, dict):
                continue
            target = b.get("target")
            if not isinstance(target, dict):
                continue
            eid = target.get("entity_id")
            cid = target.get("connection_id")
            cids = target.get("connection_ids")
            if eid and str(eid) not in entity_ids:
                entity_ids.append(str(eid))
            if cid and str(cid) not in conn_ids:
                conn_ids.append(str(cid))
            if isinstance(cids, list):
                for c in cids:
                    if str(c) not in conn_ids:
                        conn_ids.append(str(c))
        return DiagramRendererReferences(
            entity_ids=tuple(entity_ids),
            connection_ids=tuple(conn_ids),
        )

    def _render_item(self, item: _ResolvedItem, *, show_descriptions: bool = False) -> str:
        label = _escape_puml(item.label)
        tech = _escape_puml(item.technology) if item.technology else ""
        descr = _escape_puml(item.description) if show_descriptions and item.description else ""

        # Shape resolution: explicit shape → technology inference → item-type default
        if item.shape:
            macro = item.shape
            # Apply external suffix unless the caller already included it.
            if item.external and not macro.endswith("_Ext"):
                macro = macro + "_Ext"
            has_tech_arg = not macro.startswith(("Person", "System"))
        else:
            variant = _tech_variant(item.technology) if item.technology else "generic"
            macro = _c4_macro_name(item.item_type, variant, item.external)
            has_tech_arg = item.item_type not in ("person", "software-system")

        if has_tech_arg:
            if descr:
                return f'{macro}({item.alias}, "{label}", "{tech}", "{descr}")'
            return f'{macro}({item.alias}, "{label}", "{tech}")'
        if descr:
            return f'{macro}({item.alias}, "{label}", "{descr}")'
        return f'{macro}({item.alias}, "{label}")'

    def _append_hidden_chain(self, lines: list[str], aliases: list[str], *, indent: str) -> None:
        if len(aliases) < 2:
            if aliases:
                lines.append("")
            return
        for index in range(len(aliases) - 1):
            lines.append(f"{indent}{aliases[index]} -[hidden]right- {aliases[index + 1]}")
        lines.append("")


def alias_for_c4_item(item_type: str, local_id: str, index: int) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]", "_", local_id)
    prefix = "".join(part[:1].upper() for part in item_type.replace("-", "_").split("_")) or "C"
    return f"{prefix}_{normalized}_{index}"


def _render_item_body(item: _ResolvedItem, *, show_descriptions: bool = False) -> str:
    """Label text for a C4 element (name + optional description).
    Technology is a separate macro argument in C4-PlantUML stdlib calls.
    """
    parts = [_escape_puml(item.label)]
    if show_descriptions and item.description:
        parts.append(_escape_puml(item.description))
    return "\\n".join(part for part in parts if part)


def _escape_puml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', "'")

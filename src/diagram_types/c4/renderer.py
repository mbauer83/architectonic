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

from src.diagram_types.c4._projection_vocabulary import GROUP_TYPE, NODE_TYPE
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


#: Which way a generated C4 body lays out, and the key a diagram states it under. Left-to-right is
#: the default because it is what these views were drawn with and what they were read as.
#:
#: It is per diagram because it cannot be global. Bisected against this repository's own
#: `plantuml.jar`: `left to right direction` AND `linetype ortho` AND a nested cluster crashes dot —
#: all three together, on a view of eleven boxes with no hidden edges at all. Any one of the three
#: removed renders it, and the 45-box component view with four nested groups behaves identically.
#: Neither of the other two is available to give up: ortho is the only routing that has looked right
#: here, and the direction is worth keeping wherever it can be. So a diagram that nests boundaries
#: and hits the crash says so for itself, and every other diagram keeps the default.
DIRECTION_KEY = "_direction"
_DIRECTIONS: dict[str, str] = {
    "left_to_right": "left to right direction",
    "top_to_bottom": "top to bottom direction",
}


def _direction_lines(diagram_entities: Mapping[str, object]) -> list[str]:
    requested = str(diagram_entities.get(DIRECTION_KEY) or "left_to_right")
    return [_DIRECTIONS.get(requested, _DIRECTIONS["left_to_right"])]


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
    if item_type == NODE_TYPE:
        # A deployment host, and no variant or suffix applies to it. `_open_boundary` emits the same
        # macro for a host that holds something, so this is the *childless* case — and it had no row
        # here at all, falling through to the container fallback below: a volume or a machine with
        # nothing drawn inside it rendered as an application container labelled with its technology.
        #
        # Neither the store variant nor `_Ext` is taken. A node is not a database whatever it holds,
        # and `Deployment_Node_Ext` is not defined by the C4 deployment stdlib — calling it on the
        # pinned PlantUML produces no diagram at all.
        return "Deployment_Node"
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
        # Which C4-PlantUML header the body needs is the type's to say: `Deployment_Node` lives in
        # `C4_Deployment`, and including the component header for a deployment view would leave the
        # macro undefined and the diagram rendering as an error image rather than failing.
        c4_config: dict[str, Any] = self._config.get("c4") or {}
        lines: list[str] = [
            f"@startuml {diagram_name}",
            f"!include <C4/{c4_config.get('puml_stdlib') or 'C4_Component'}>",
            *_direction_lines(diagram_entities or {}),
            "skinparam shadowing false",
            "skinparam linetype ortho",
            "skinparam defaultTextAlignment center",
            *label_wrap_skinparams(self._config),
            "",
            f"title {name}",
            "",
        ]

        show_desc = bool(c4_config.get("show_node_descriptions", False))

        # Hidden chains that order top-level elements are collected here and emitted *after* the
        # visible edges, which is the whole of what keeps this diagram renderable.
        #
        # Declared before them, the same 38 hidden edges over the same 41 boxes crashed dot's
        # orthogonal router — reproducibly, three runs out of three — and PlantUML answers that by
        # drawing the stack trace as the picture. Moving the identical lines below the `-->` lines
        # renders. It is not a size limit: the version before this one carried 58 hidden edges over
        # 56 boxes in the same diagram and drew fine, and each half of the crashing pair drew fine
        # alone. Order is the variable, so order is what is fixed here.
        #
        # A chain inside a boundary cannot move — the brace closes above the edges — so that one
        # stays where it is declared. No chain touches a boundary alias or runs between two of them:
        # a `-[hidden]-` edge across a cluster wall is its own crash, shape-dependent and separate
        # from this one.
        top_level_chains: list[str] = []
        if state.scope_render_mode == "deployment":
            # The system in scope is the title, not a box: what the reader is being shown is where
            # its containers run, so each hosting node is the boundary and the containers sit in it.
            for host in state.internal_items:
                self._append_nested(lines, host, indent="", show_descriptions=show_desc)
        elif state.scope_render_mode == "node":
            # Every scope item is drawn: one system at context level, a portfolio of them at
            # landscape level. A boundary can only wrap one thing, which is why the two modes and
            # the two scope cardinalities divide along the same line.
            for item in state.scope_items:
                lines.append(self._render_item(item, show_descriptions=show_desc))
            self._append_hidden_chain(
                top_level_chains, [i.alias for i in state.scope_items], indent="",
            )
        else:
            lines.append(
                f'System_Boundary({state.scope_item.alias}, "{_escape_puml(state.scope_item.label)}") {{'
            )
            for item in state.internal_items:
                self._append_nested(lines, item, indent="  ", show_descriptions=show_desc)
            self._append_hidden_chain(lines, [i.alias for i in state.internal_items], indent="  ")
            lines.append("}")
        lines.append("")

        outside_items = state.outside_items
        if outside_items:
            for item in outside_items:
                lines.append(self._render_item(item, show_descriptions=show_desc))
            lines.append("")
            # Two chains, never one running through the scope. Threading people → boundary →
            # systems onto a single line made the boundary alias — a cluster — an endpoint, and
            # forced every rank it touched: that is what stacked eight actors into a column taller
            # than the system they use. People and third-party systems are not siblings of each
            # other, and the drawn edges already say which side of the system each one is on.
            self._append_hidden_chain(
                top_level_chains, [i.alias for i in outside_items if i.item_type == "person"], indent="",
            )
            self._append_hidden_chain(
                top_level_chains, [i.alias for i in outside_items if i.item_type != "person"], indent="",
            )
        for conn in state.connections:
            raw_label = (
                edge_labels.get(f"{conn.src_alias}:{conn.tgt_alias}", conn.label)
                if edge_labels
                else conn.label
            )
            # No label means no ` : ` either. `A --> B : ` reserves label space GraphViz then
            # routes around, so an empty one costs the layout as much as a real one and says less.
            if raw_label:
                lines.append(f"{conn.src_alias} --> {conn.tgt_alias} : {_escape_puml(raw_label)}")
            else:
                lines.append(f"{conn.src_alias} --> {conn.tgt_alias}")
        if top_level_chains:
            lines.append("")
            lines.extend(top_level_chains)
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
            eids = target.get("entity_ids")
            cid = target.get("connection_id")
            cids = target.get("connection_ids")
            if eid and str(eid) not in entity_ids:
                entity_ids.append(str(eid))
            if isinstance(eids, list):
                for e in eids:
                    if str(e) not in entity_ids:
                        entity_ids.append(str(e))
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
            variant = "db" if item.is_store else (
                _tech_variant(item.technology) if item.technology else "generic"
            )
            macro = _c4_macro_name(item.item_type, variant, item.external)
            has_tech_arg = item.item_type not in ("person", "software-system")

        if has_tech_arg:
            if descr:
                return f'{macro}({item.alias}, "{label}", "{tech}", "{descr}")'
            return f'{macro}({item.alias}, "{label}", "{tech}")'
        if descr:
            return f'{macro}({item.alias}, "{label}", "{descr}")'
        return f'{macro}({item.alias}, "{label}")'

    def _append_nested(
        self, lines: list[str], item: _ResolvedItem, *, indent: str, show_descriptions: bool
    ) -> None:
        """One element and everything drawn inside it, however deep the nesting goes.

        Two things open a boundary rather than draw a box, and they are the same shape of statement:
        a deployment node, which holds what runs on it, and a grouping, which holds what belongs
        together. C4 calls the second a *group* and is explicit that it "will be rendered as a
        boundary around those elements" and is not an element of the model at all — so it is emitted
        with the generic `Boundary()` macro and never with a component's.

        Recursive because both nest: a host holds a container runtime which holds the containers, and
        a group may hold a subgroup. Drawing one level flattened a deployment into "these run side by
        side on a machine", which is a different claim.

        The hidden chain that orders siblings is emitted *inside* each boundary and never across
        two. A `-[hidden]-` edge that crosses cluster walls crashes GraphViz in a way that depends
        on the shapes involved, so it surfaces as a rendered error image rather than a failure.

        """
        if not item.children:
            lines.append(f"{indent}{self._render_item(item, show_descriptions=show_descriptions)}")
            return
        lines.append(f"{indent}{self._open_boundary(item)}")
        inner = indent + "  "
        for child in item.children:
            self._append_nested(lines, child, indent=inner, show_descriptions=show_descriptions)
        self._append_hidden_chain(lines, [child.alias for child in item.children], indent=inner)
        lines.append(f"{indent}}}")

    def _open_boundary(self, item: _ResolvedItem) -> str:
        """The macro that opens a boundary for an element that holds others."""
        label = _escape_puml(item.label)
        if item.item_type == GROUP_TYPE:
            return f'Boundary({item.alias}, "{label}", "group") {{'
        return f'Deployment_Node({item.alias}, "{label}", "{_escape_puml(item.technology or item.item_type)}") {{'

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

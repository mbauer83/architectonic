"""Failure-mode matrix diagram type — bespoke frontend grid renderer.

The frontend renders this as an interactive grid: rows are the candidate elements crossed with the
five failure guidewords, columns are the effect, cause, prevention and detection controls, the
three factors, the Action Priority and the targeting signals. PlantUML rendering is explicitly
unsupported; `render_body` raises so the PUML pipeline cannot be invoked against it.

Store-projected, which is what keeps confidential content out of the file-backed diagram browser:
implementing `project_store_graph` is how a diagram type declares that its content comes from the
confidential store rather than from git-tracked files.

module_class = "assurance"; requires the confidential store.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.diagram_types._assurance_analysis_scope import analysis_methods_from
from src.diagram_types._base import DiagramTypeBase
from src.domain.assurance.failure_modes import FAILURE_GUIDEWORD_SLUGS
from src.domain.modules.module_types import ConnectionTypeName, DiagramTypeName, EntityTypeName, FreeOntology
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.ontology_representation.ontology_protocol import (
    DiagramRenderer,
    DiagramTypeModule,
    DiagramTypeWriteGuidance,
)
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, EntityTypeInfo
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet
from src.domain.yaml_documents import parse_yaml

_EMPTY_ENTITY_TYPES: dict[EntityTypeName, EntityTypeInfo] = {}
_EMPTY_CONNECTION_TYPES: dict[ConnectionTypeName, ConnectionTypeInfo] = {}

#: The node types a row is built from. A failure mode's effect is a hazard and its consequence a
#: loss, both of which the grid shows; its prevention and detection controls are constraints.
_PARTICIPATING = frozenset({"failure-mode", "hazard", "loss", "assurance-constraint", "loss-scenario"})

#: The relations that place something in the grid. Everything else a failure mode touches belongs
#: to the causal chain rather than to this table, and would add cells nothing reads.
_GRID_RELATIONS = frozenset({"leads-to", "detects", "derives", "explains"})


class _FmeaMatrixRenderer:
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
        del name, entities, connections, diagram_type, repo_root, diagram_entities, diagram_connections
        raise ValueError("FMEA matrix diagrams use the failure-mode grid renderer")

    def inject_includes(self, body: str, repo_root: Path) -> str:
        del repo_root
        return body


class _FmeaMatrixDiagramType(DiagramTypeBase):
    module_class = "assurance"
    requires: list[str] = ["confidential_store"]

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    def project_store_graph(
        self,
        nodes: Sequence[Mapping[str, object]],
        edges: Sequence[Mapping[str, object]],
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        """The sub-graph the failure-mode grid is built from."""
        participating = [
            dict(n) for n in nodes if str(n.get("node_type", "")) in _PARTICIPATING
        ]
        ids = {str(n["node_id"]) for n in participating}
        between = [
            dict(e) for e in edges
            if str(e.get("conn_type", "")) in _GRID_RELATIONS
            and str(e.get("source_id", "")) in ids
            and str(e.get("target_id", "")) in ids
        ]
        return participating, between

    @property
    def analysis_methods(self) -> frozenset[str]:
        return analysis_methods_from(self._config)

    @property
    def name(self) -> DiagramTypeName:
        return DiagramTypeName(str(self._config["name"]))

    @property
    def primary_ontology(self):  # type: ignore[override]
        return FreeOntology

    @property
    def own_entity_types(self) -> dict[EntityTypeName, EntityTypeInfo]:
        return _EMPTY_ENTITY_TYPES

    @property
    def own_connection_types(self) -> dict[ConnectionTypeName, ConnectionTypeInfo]:
        return _EMPTY_CONNECTION_TYPES

    @property
    def own_permitted_relationships(self) -> PermittedRelationshipSet:
        return PermittedRelationshipSet.empty()

    @property
    def renderer(self) -> DiagramRenderer:
        return _FmeaMatrixRenderer()

    def write_guidance(self) -> DiagramTypeWriteGuidance:
        return DiagramTypeWriteGuidance(
            when_to_use=(
                "Use to display the failure-mode grid: rows=architecture elements crossed with the "
                f"failure guidewords ({', '.join(FAILURE_GUIDEWORD_SLUGS)}), columns=effect, cause, "
                "prevention, detection, severity, occurrence, detectability and Action Priority. "
                "The frontend renders this as an interactive grid."
            ),
            when_not_to_use=(
                "Do not use for PlantUML rendering pipelines. This diagram type has no PUML body; "
                "any attempt to call render_body raises ValueError by design. Do not use it to show "
                "the causal chain either — a bowtie or the graph explorer shows that, and this grid "
                "deliberately omits every relation that does not place something in a cell."
            ),
            puml_notes=(
                "There is no PUML body and no `diagram_entities` to author. The grid is PROJECTED"
                " from the confidential assurance store: fill it with the assurance write tools —"
                " `assurance_create_node` for failure modes, hazards, losses and constraints,"
                " `assurance_add_edge` for the relations below, and `assurance_set_fmea_factor` for"
                " severity, occurrence and detectability.",
                "A row is an architecture element crossed with a failure guideword; the columns are"
                " the effect, the cause, the prevention and detection controls, the three factors,"
                " and the Action Priority derived from them. Only four relations place anything:"
                " `leads-to`, `detects`, `derives` and `explains`. Every other relation a failure"
                " mode has belongs to the causal chain and is omitted on purpose.",
                "Action Priority is derived from the three factors, never authored: set the factors"
                " and the column follows. A row whose factors are unset shows the gap rather than a"
                " default, which is the point of the grid.",
                "Nothing renders to disk — the diagram is served from the store to the frontend"
                " grid, and the renderer raises rather than returning an empty body, so the"
                " confidential content cannot reach the file-backed catalog through this path.",
            ),
        )


def _load_config(package_dir: Path) -> dict[str, Any]:
    config_path = package_dir / "config.yaml"
    with config_path.open(encoding="utf-8") as handle:
        return parse_yaml(handle) or {}


module: DiagramTypeModule = _FmeaMatrixDiagramType(_load_config(Path(__file__).parent))

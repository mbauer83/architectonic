"""UCA matrix diagram type — bespoke frontend grid renderer.

The frontend renders UCA matrices as an interactive markdown-style grid
(control-action × guideword). PlantUML rendering is explicitly unsupported;
render_body raises ValueError to prevent the PUML pipeline from being invoked.

module_class = "assurance"; requires the confidential store.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from src.diagram_types._assurance_analysis_scope import analysis_methods_from
from src.diagram_types._base import DiagramTypeBase
from src.domain.assurance.uca_guidewords import UCA_GUIDEWORD_SLUGS
from src.domain.modules.module_types import ConnectionTypeName, DiagramTypeName, EntityTypeName, FreeOntology
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.ontology_representation.ontology_protocol import (
    DiagramRenderer,
    DiagramTypeModule,
    DiagramTypeWriteGuidance,
)
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, EntityTypeInfo
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet

_EMPTY_ENTITY_TYPES: dict[EntityTypeName, EntityTypeInfo] = {}
_EMPTY_CONNECTION_TYPES: dict[ConnectionTypeName, ConnectionTypeInfo] = {}


class _UcaMatrixRenderer:
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
        raise ValueError("UCA matrix diagrams use the markdown UCA grid renderer")

    def inject_includes(self, body: str, repo_root: Path) -> str:
        del repo_root
        return body


class _UcaMatrixDiagramType(DiagramTypeBase):
    module_class = "assurance"
    requires: list[str] = ["confidential_store"]

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    def project_store_graph(
        self,
        nodes: Sequence[Mapping[str, object]],
        edges: Sequence[Mapping[str, object]],
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        """The sub-graph the UCA grid is built from: control actions, the unsafe control actions
        enumerated against them, and only the `concerns` edges that place a UCA in a row.

        Every other relation a UCA has — to its controller, to the hazards it leads to — belongs to
        the causal chain, not to this grid, and would only add cells nothing reads.
        """
        participating = [
            dict(n) for n in nodes
            if str(n.get("node_type", "")) in {"control-action", "unsafe-control-action"}
        ]
        ids = {str(n["node_id"]) for n in participating}
        between = [
            dict(e) for e in edges
            if str(e.get("conn_type", "")) == "concerns"
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
        return _UcaMatrixRenderer()

    def write_guidance(self) -> DiagramTypeWriteGuidance:
        return DiagramTypeWriteGuidance(
            when_to_use=(
                "Use to display the UCA grid: rows=control-actions, columns=uca-types "
                f"({', '.join(UCA_GUIDEWORD_SLUGS)}). "
                "The frontend renders this as an interactive markdown grid."
            ),
            when_not_to_use=(
                "Do not use for PlantUML rendering pipelines. This diagram type has no PUML "
                "body; any attempt to call render_body raises ValueError by design."
            ),
            puml_notes=(
                "There is no PUML body and no `diagram_entities` to author. The grid is PROJECTED"
                " from the confidential assurance store, so it is filled by creating the analysis"
                " content through the assurance write tools — `assurance_create_node` for the"
                " control actions and the unsafe control actions enumerated against them,"
                " `assurance_add_edge` for the `concerns` edges — not by writing the diagram.",
                "A row is a control action; a column is a UCA guideword; a cell is the unsafe"
                " control action that `concerns` that action under that guideword. Only `concerns`"
                " edges place anything: a UCA's other relations — to its controller, to the hazards"
                " it leads to — belong to the causal chain and are deliberately not shown here.",
                "Nothing renders to disk. The diagram is served from the store to the frontend grid,"
                " which is what keeps confidential content out of the file-backed catalog; a"
                " rendered PNG or SVG of this type would breach that boundary, which is why the"
                " renderer raises rather than returning an empty body.",
            ),
        )


def _load_config(package_dir: Path) -> dict[str, Any]:
    config_path = package_dir / "config.yaml"
    with config_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


module: DiagramTypeModule = _UcaMatrixDiagramType(_load_config(Path(__file__).parent))

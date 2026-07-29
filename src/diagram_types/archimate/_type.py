"""Helpers for config-backed ArchiMate diagram types."""

from __future__ import annotations

from pathlib import Path

from src.diagram_types._config_type import _ConfiguredOntologyDiagramType, _load_config, _load_ontology_module
from src.domain.ontology_representation.ontology_protocol import (
    DiagramRenderer,
    DiagramTypeModule,
    DiagramTypeWriteGuidance,
)


class _ConfiguredArchimateDiagramType(_ConfiguredOntologyDiagramType):
    @property
    def renderer(self) -> DiagramRenderer:
        from src.infrastructure.rendering.archimate_puml_renderer import ArchimatePumlRenderer  # noqa: PLC0415

        return ArchimatePumlRenderer(self._config)

    def write_guidance(self) -> DiagramTypeWriteGuidance:
        base = super().write_guidance()
        return DiagramTypeWriteGuidance(
            when_to_use=base.when_to_use,
            when_not_to_use=base.when_not_to_use,
            accepted_domains=base.accepted_domains,
            diagram_entities_schema=base.diagram_entities_schema,
            own_entity_types=base.own_entity_types,
            puml_notes=(
                "ArchiMate connection descriptions are hidden by default."
                " Only render selected connection text when the diagram explicitly opts in.",
                "For manual PUML, keep model selectability by using real model entity aliases as arrow endpoints."
                " Explicit arrows are selectable based on endpoint alias matching regardless of label text"
                " — stereotype prefixes like <<serving>> are not required and should be omitted for cleaner diagrams."
                " Use --> for serving relations and -- for association relations.",
                "For ArchiMate diagrams, diagram_connections may be used as per-diagram connection annotation"
                " metadata keyed by model connection artifact_id. Supported opt-in keys are artifact_id"
                " (or connection_id), include_description, include_multiplicity, and label."
                " The show_stereotype key is not needed since stereotype text is not required for selectability.",
                "For additional occurrences of an already included model entity, add"
                " diagram_entities.occurrence[] items with id and backing_entity_id. The id is the"
                " occurrence identity; backing_entity_id is the model entity to render again. visual_role"
                " is optional human-readable metadata, not the occurrence identifier.",
            ),
        )


def load_archimate_diagram_type(package_dir: Path) -> DiagramTypeModule:
    config = _load_config(package_dir)
    ontology_name = str(config.get("ontology") or "").strip()
    if not ontology_name:
        raise ValueError(f"Diagram type config at {package_dir / 'config.yaml'} must define an 'ontology' package")
    return _ConfiguredArchimateDiagramType(config, _load_ontology_module(ontology_name))

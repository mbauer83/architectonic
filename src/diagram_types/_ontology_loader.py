"""Read a diagram type's ontology declaration."""

from pathlib import Path

from src.domain.diagrams.diagram_ontology_loader import DiagramOntology, diagram_ontology_from_mapping
from src.domain.yaml_documents import parse_yaml


def load_diagram_ontology(path: Path) -> DiagramOntology:
    with path.open(encoding="utf-8") as stream:
        return diagram_ontology_from_mapping(parse_yaml(stream) or {})

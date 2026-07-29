from __future__ import annotations

from pathlib import Path

from src.diagram_types.archimate._type import load_archimate_diagram_type
from src.domain.ontology_representation.ontology_protocol import DiagramTypeModule

module: DiagramTypeModule = load_archimate_diagram_type(Path(__file__).parent)

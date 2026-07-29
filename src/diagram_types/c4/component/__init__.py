from pathlib import Path

from src.diagram_types.c4._type import load_c4_diagram_type
from src.domain.ontology_representation.ontology_protocol import DiagramTypeModule

module: DiagramTypeModule = load_c4_diagram_type(Path(__file__).parent)

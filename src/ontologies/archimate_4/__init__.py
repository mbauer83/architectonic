"""ArchiMate 4.0 ontology module."""

from pathlib import Path

from src.domain.ontology_representation.ontology_protocol import OntologyModule
from src.ontologies.archimate_4._loader import load_archimate_4_module

_mod = load_archimate_4_module(Path(__file__).parent)
module: OntologyModule = _mod  # type: ignore[assignment]
matrix_abbreviations: dict[str, str] = _mod.matrix_abbreviations

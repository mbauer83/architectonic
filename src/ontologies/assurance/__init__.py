"""Assurance ontology module (STPA / CAST / GRC entity and connection types)."""

from pathlib import Path

from src.domain.ontology_representation.ontology_protocol import OntologyModule
from src.ontologies.assurance._loader import load_assurance_module

_mod = load_assurance_module(Path(__file__).parent)
module: OntologyModule = _mod  # type: ignore[assignment]

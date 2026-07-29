"""SysML v2 minimum ontology module — bounded first slice for structure, behavior,
interface, data, and requirements.  Interoperates with ArchiMate via bridge bindings
(task #18) rather than shared type inheritance.
"""

from pathlib import Path

from src.domain.ontology_representation.ontology_protocol import OntologyModule
from src.ontologies.sysml_v2_min._loader import load_sysml_module

module: OntologyModule = load_sysml_module(Path(__file__).parent)  # type: ignore[assignment]

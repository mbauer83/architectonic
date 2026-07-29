"""Legal edge types for a node-type pair from the LOADED assurance module —
the single ontology source shared by every write transport (HTTP, MCP); no
literal list exists at any transport layer."""

from __future__ import annotations

from src.application.assurance_edge_catalog import legal_connection_types_for
from src.infrastructure.app_bootstrap import assurance_ontology_module


def legal_connection_types(source_type: str, target_type: str) -> frozenset[str]:
    return legal_connection_types_for(assurance_ontology_module())(source_type, target_type)

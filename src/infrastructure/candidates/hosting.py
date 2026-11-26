"""Which stored diagrams a candidate may be drawn on: those whose diagram type says it hosts candidates.

The diagram-type catalogue owns the answer (`DiagramTypeModule.hosts_candidates`); this is the one place a
candidate's diagram is held to it, for every transport and for every way a candidate comes to be drawn on a
diagram — created on one, edited onto one, or compared on one.
"""

from __future__ import annotations

from src.domain.ontology_representation.artifact_types import DiagramRecord
from src.infrastructure.app_bootstrap import process_runtime_catalogs


def hosts_candidates(diagram_type: str) -> bool:
    """Whether a diagram of *diagram_type* may have a candidate drawn on it; False for a type not registered."""
    kind = process_runtime_catalogs().diagram_types.find_diagram_type(diagram_type)
    return kind is not None and kind.hosts_candidates


def refuse_unless_it_hosts(diagram: DiagramRecord) -> DiagramRecord:
    """*diagram*, refused (ValueError) where its type does not host candidates, with the types that do."""
    if hosts_candidates(diagram.diagram_type):
        return diagram
    hosting = sorted(
        name for name, kind in process_runtime_catalogs().diagram_types.all_diagram_types().items()
        if kind.hosts_candidates
    )
    raise ValueError(
        f"{diagram.artifact_id} is a {diagram.diagram_type} diagram, which a candidate cannot be drawn on: a "
        f"candidate is drawn on a picture of the model's elements and relations ({', '.join(hosting)})."
    )

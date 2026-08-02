"""When the entities a caller chose cannot make the diagram they asked for.

A diagram type is entitled to refuse a selection: a C4 context diagram scoped to an entity the
repository does not hold, a standalone C4 with no item of its scope type. Those are statements
about the *request*, and the addressing rules make them a 400.

They were plain ``ValueError``\\ s, indistinguishable at the boundary from the other thing a
diagram type raises with — a config.yaml that declares no ontology, an unknown analysis method,
a renderer reached through the wrong entry point. Those are statements about the *deployment*,
and a 500 is the honest answer to them. One exception type for both meant the handler had to
choose which lie to tell; ``/api/diagrams/preview`` chose 500, so a caller who supplied a scope
entity of the wrong type was told the server was broken and the diagnostic stayed in the log.

Subclasses ``ValueError`` so every existing ``except ValueError`` still catches it — the split is
additive, and nothing that already handled these has to learn a second name.
"""

from __future__ import annotations


class DiagramSelectionError(ValueError):
    """The caller's diagram-entity selection is not one this diagram type can draw."""

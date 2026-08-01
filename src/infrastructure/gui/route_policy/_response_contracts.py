"""Operations declared ``typed`` that do not yet serve a named, closed component.

The measure of the response-contract work remaining, and nothing more than that. It used to mean
something subtly different and much less useful — "the DTO *name* in the manifest row is not the
component being served" — which made every entry an adjudication: was the handler wrong, or was the
name a Phase 0 guess about a shape nobody had modelled? Three times it was the name, and each time the
work stopped to ask. The manifest now declares a *kind* rather than a name, so an entry here says one
thing: this handler answers with an open model, an inline schema, or nothing at all, and it should
answer with a closed DTO derived from what it returns.

It shrinks per surface as each is authored, and it is **empty** when the contract is complete. Nothing
may be added: a new operation declares its DTO when it is written, which is cheap then and expensive
later.
"""

from __future__ import annotations

#: Operation ids whose declared success body is not yet the DTO the manifest names.
UNTYPED_RESPONSE_OPERATIONS: frozenset[str] = frozenset({
    "diagrams_discover_diagram_entities",
    "diagrams_preview_diagram",
    "diagrams_read_diagram",
    "diagrams_read_diagram_context",
    "diagrams_search_entity_display_items",
    "documents_read_document_schemata",
    "taxonomy_read_authoring_guidance",
    "viewpoints_execute_viewpoint_diagram",
    "viewpoints_list_viewpoints",
    "viewpoints_read_criteria_catalog",
    "viewpoints_summarize_viewpoint",
})

from pathlib import Path

from src.domain.ontology_representation.artifact_types import DocumentRecord, EntityRecord, SearchHit
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.rest.routers._global_search import prioritize_global_hits, visible_diagram_entity_types


def _entity(artifact_id: str, *, host_diagram_id: str | None = None) -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type="application-component",
        name=artifact_id,
        version="0.1.0",
        status="active",
        domain="application",
        subdomain="components",
        path=Path("/tmp/entity.md"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label=artifact_id,
        display_alias="APP",
        host_diagram_id=host_diagram_id,
    )


def test_model_entities_precede_diagram_owned_records() -> None:
    """A diagram-owned entity is demoted; nothing else moves.

    The expectation here was restated once already rather than quietly corrected: it used to require a
    document scoring 9.0 to come back *below* an entity scoring 7.0, because every non-entity record
    was bucketed behind every entity. That is how a diagram searched for by its exact title returned
    forty entities and none of it. The concern the bucketing really expressed is narrower — a
    diagram-local node is a drawing detail, a model entity is a commitment — and it applies to
    entities only. Cross-kind order belongs to `_rank_balanced`.

    That restatement left a function whose body was only this docstring, immediately followed by the
    next `def` — so it declared an expectation and asserted nothing, and passed for it.
    """
    document = DocumentRecord(
        artifact_id="DOC@1",
        doc_type="spec",
        title="Architecture Backend",
        status="active",
        path=Path("/tmp/doc.md"),
        keywords=(),
        sections=(),
        content_text="",
        extra={},
    )
    hits = [
        SearchHit(9.0, "document", document),
        SearchHit(8.0, "entity", _entity("LOCAL@1", host_diagram_id="DIA@1")),
        SearchHit(7.0, "entity", _entity("APP@1")),
    ]

    ordered = prioritize_global_hits(hits)

    assert [hit.record.artifact_id for hit in ordered] == ["DOC@1", "APP@1", "LOCAL@1"]


def test_no_diagram_owned_type_opts_into_global_search_by_default() -> None:
    """Visibility is now decided upstream, so what this asserts is the *vocabulary* the route hands
    to the one predicate — not a filter applied to already-ranked hits.

    It used to assert that a late filter removed a diagram-owned hit. That filter is gone: it keyed
    on `host_diagram_id` while the exclusion upstream keyed on declared type names, and the two
    disagreeing is what let invisible records consume the window and shorten the answer.
    """
    catalogs = build_runtime_catalogs(get_module_registry())

    assert visible_diagram_entity_types(catalogs) == frozenset()

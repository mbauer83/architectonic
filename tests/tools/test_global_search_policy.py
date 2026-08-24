from pathlib import Path

from src.domain.ontology_representation.artifact_types import DocumentRecord, EntityRecord, SearchHit
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.rest.routers._global_search import filter_global_hits, prioritize_global_hits


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


def test_a_diagram_owned_entity_is_demoted_and_nothing_else_is() -> None:
    """This test asserted the defect, so the expectation is restated rather than quietly corrected.

    It required a document scoring 9.0 to come back *below* an entity scoring 7.0, because every
    non-entity record was bucketed behind every entity. That is how a diagram searched for by its
    exact title returned forty entities and none of it: the window filled with entities before the
    kind the index had ranked first could be reached.

    The concern the bucketing was really expressing is narrower — a diagram-local node is a drawing
    detail, a model entity is a commitment — and it applies to entities only. Cross-kind order belongs
    to `_rank_balanced`, which round-robins precisely because the scores are incomparable.
    """
def test_model_entities_precede_diagram_owned_records() -> None:
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


def test_undeclared_diagram_owned_types_are_hidden_by_default() -> None:
    hits = [
        SearchHit(8.0, "entity", _entity("LOCAL@1", host_diagram_id="DIA@1")),
        SearchHit(7.0, "entity", _entity("APP@1")),
    ]

    catalogs = build_runtime_catalogs(get_module_registry())
    visible = filter_global_hits(hits, catalogs)

    assert [hit.record.artifact_id for hit in visible] == ["APP@1"]

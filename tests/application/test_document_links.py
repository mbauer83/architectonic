from __future__ import annotations

from pathlib import Path

from src.application.document_links import references_to_entity
from src.domain.ontology_representation.artifact_types import DocumentRecord, EntityRecord


def test_references_to_entity_reports_document_section(tmp_path: Path) -> None:
    entity_path = tmp_path / "model" / "motivation" / "requirement" / "REQ@1.a.target.md"
    doc_path = tmp_path / "docs" / "adr" / "ADR@1.b.decision.md"
    entity = EntityRecord(
        artifact_id="REQ@1.a.target",
        artifact_type="requirement",
        name="Target",
        version="0.1.0",
        status="active",
        domain="motivation",
        subdomain="",
        path=entity_path,
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label="Target",
        display_alias="",
    )
    doc = DocumentRecord(
        artifact_id="ADR@1.b.decision",
        doc_type="adr",
        title="Decision",
        status="accepted",
        path=doc_path,
        keywords=(),
        sections=("Context",),
        content_text=(
            "## Context\n"
            "The [target](../../model/motivation/requirement/REQ@1.a.target.md) matters.\n"
            "Ignore [site](https://example.com).\n"
        ),
        extra={},
    )

    refs = references_to_entity(documents=[doc], entity=entity)

    assert [ref.to_dict() for ref in refs] == [
        {
            "document_id": "ADR@1.b.decision",
            "title": "Decision",
            "doc_type": "adr",
            "path": str(doc_path),
            "section": "Context",
            "label": "target",
            "href": "../../model/motivation/requirement/REQ@1.a.target.md",
        }
    ]

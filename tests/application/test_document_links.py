from __future__ import annotations

from pathlib import Path

from src.application.document_links import references_from, references_to_entity
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


class TestOneReadingOfWhatAProseLinkPointsAt:
    """The reading three callers had spelled for themselves, stated over what a link may be.

    The case that matters most is the anchored one. The cascade-delete preflight matched
    `](….md)` with a regex of its own, which cannot match `](….md#properties)` at all — so a
    document linking into a *section* of an entity was invisible to the check whose whole job is
    to find what a deletion would break.
    """

    def test_a_relative_link_resolves_against_the_document_that_makes_it(self, tmp_path: Path) -> None:
        directory = tmp_path / "docs" / "adr"

        refs = references_from("see [Target](../../model/REQ@1.a.target.md)", directory=directory)

        assert [ref.target for ref in refs] == [(tmp_path / "model" / "REQ@1.a.target.md").resolve()]

    def test_an_anchor_names_a_place_inside_the_file_the_link_resolves_to(self, tmp_path: Path) -> None:
        directory = tmp_path / "docs"

        refs = references_from("[Target](REQ@1.a.target.md#properties)", directory=directory)

        assert [ref.target for ref in refs] == [(tmp_path / "docs" / "REQ@1.a.target.md").resolve()]
        assert refs[0].href == "REQ@1.a.target.md#properties"

    def test_an_external_or_anchor_only_link_addresses_no_file(self, tmp_path: Path) -> None:
        content = (
            "[web](https://example.invalid/x.md) [insecure](http://example.invalid/y.md) "
            "[here](#section) [mail](mailto:someone@example.invalid)"
        )

        assert references_from(content, directory=tmp_path) == []

    def test_the_label_and_offset_survive_so_a_caller_can_say_where_it_sits(self, tmp_path: Path) -> None:
        content = "## Decision\n\nsee [The Target](x.md)"

        reference = references_from(content, directory=tmp_path)[0]

        assert reference.label == "The Target"
        assert content[reference.start:].startswith("[The Target]")


class TestTheCascadePreflightSeesWhatTheReadingSees:
    def test_a_link_into_a_section_of_a_doomed_entity_is_reported(self, tmp_path: Path) -> None:
        """The defect the consolidation fixes: its own regex could not match this at all."""
        from src.infrastructure.write.artifact_write._cascade_helpers import find_broken_links

        entity = tmp_path / "model" / "REQ@1.a.target.md"
        entity.parent.mkdir(parents=True)
        entity.write_text("---\nartifact-id: REQ@1.a.target\n---\n", encoding="utf-8")
        doc = tmp_path / "docs" / "ADR@1.b.decision.md"
        doc.parent.mkdir(parents=True)
        doc.write_text("[Target](../model/REQ@1.a.target.md#properties)\n", encoding="utf-8")

        broken = find_broken_links(doc, {entity.resolve()}, tmp_path)

        assert broken == ["../model/REQ@1.a.target.md#properties"]

    def test_a_plain_link_to_a_doomed_entity_is_still_reported(self, tmp_path: Path) -> None:
        from src.infrastructure.write.artifact_write._cascade_helpers import find_broken_links

        entity = tmp_path / "model" / "REQ@1.a.target.md"
        entity.parent.mkdir(parents=True)
        entity.write_text("x", encoding="utf-8")
        doc = tmp_path / "docs" / "ADR@1.b.decision.md"
        doc.parent.mkdir(parents=True)
        doc.write_text("[Target](../model/REQ@1.a.target.md)\n", encoding="utf-8")

        assert find_broken_links(doc, {entity.resolve()}, tmp_path) == [
            "../model/REQ@1.a.target.md"
        ]

    def test_a_link_to_something_the_delete_does_not_touch_is_left_alone(self, tmp_path: Path) -> None:
        from src.infrastructure.write.artifact_write._cascade_helpers import find_broken_links

        doc = tmp_path / "docs" / "ADR@1.b.decision.md"
        doc.parent.mkdir(parents=True)
        doc.write_text("[Other](../model/REQ@9.z.other.md)\n", encoding="utf-8")

        assert find_broken_links(doc, {(tmp_path / "model" / "REQ@1.a.target.md").resolve()}, tmp_path) == []

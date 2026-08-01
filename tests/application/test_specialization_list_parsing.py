"""A concept may carry several specializations (ArchiMate §15.2). Frontmatter and
the per-connection metadata block accept a list; a bare scalar keeps working and reads as a
one-element set, so no existing repo needs migration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts._query_helpers import read_connection
from src.application.artifacts.parsing import parse_entity, parse_outgoing_file
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _parse(tmp_path: Path, spec_line: str) -> EntityRecord:
    path = tmp_path / "model" / "e.md"
    _write(
        path,
        "---\nartifact-id: APP@1.aaaaaa.thing\nartifact-type: application-component\n"
        'name: "Thing"\nversion: 0.1.0\nstatus: draft\n'
        f"{spec_line}"
        "---\n<!-- §content -->\n\n## Thing\n",
    )
    rec = parse_entity(path, tmp_path, domain_names=frozenset({"application"}))
    assert rec is not None
    return rec


class TestEntityFrontmatter:
    def test_scalar_round_trips_as_a_one_element_set(self, tmp_path: Path) -> None:
        rec = _parse(tmp_path, "specialization: service\n")
        assert rec.specialization == "service"
        assert rec.specializations == ("service",)

    def test_absent_specialization_is_empty_on_both_views(self, tmp_path: Path) -> None:
        rec = _parse(tmp_path, "")
        assert rec.specialization == ""
        assert rec.specializations == ()

    def test_a_list_reads_in_order(self, tmp_path: Path) -> None:
        rec = _parse(tmp_path, "specialization:\n  - service\n  - audited\n")
        assert rec.specializations == ("service", "audited")
        assert rec.specialization == "service"  # the primary is the first

    def test_a_list_is_de_duplicated_and_blanks_dropped(self, tmp_path: Path) -> None:
        rec = _parse(tmp_path, "specialization:\n  - service\n  - ''\n  - service\n  - audited\n")
        assert rec.specializations == ("service", "audited")


class TestConnectionMetadata:
    def _outgoing(self, path: Path, spec_block: str) -> None:
        _write(
            path,
            "---\nsource-entity: GRP@1.aaaaaa.g\nversion: 0.1.0\nstatus: draft\n---\n"
            "<!-- §connections -->\n\n"
            "### archimate-assignment → REQ@1.bbbbbb.r\n\n"
            f"```yaml\n{spec_block}```\n\ndesc\n",
        )

    def test_scalar_specialization_round_trips(self, tmp_path: Path) -> None:
        self._outgoing(tmp_path / "c.outgoing.md", "specialization: responsibility-assignment\n")
        recs = parse_outgoing_file(tmp_path / "c.outgoing.md")
        assert isinstance(recs[0], ConnectionRecord)
        assert recs[0].specialization == "responsibility-assignment"
        assert recs[0].specializations == ("responsibility-assignment",)

    def test_list_specialization_reads_in_order(self, tmp_path: Path) -> None:
        self._outgoing(
            tmp_path / "c.outgoing.md",
            "specialization:\n  - responsibility-assignment\n  - behavior-assignment\n",
        )
        recs = parse_outgoing_file(tmp_path / "c.outgoing.md")
        assert recs[0].specializations == ("responsibility-assignment", "behavior-assignment")

    def test_schema_metadata_is_available_on_the_record(self, tmp_path: Path) -> None:
        self._outgoing(
            tmp_path / "c.outgoing.md",
            "specialization: responsibility-assignment\npolarity: positive\nweight: 2\n",
        )
        record = parse_outgoing_file(tmp_path / "c.outgoing.md")[0]
        assert record.attributes == {"polarity": "positive", "weight": 2}
        assert read_connection(record, mode="summary")["attributes"] == {
            "polarity": "positive",
            "weight": 2,
        }


class TestRecordInvariant:
    def test_setting_only_the_list_derives_the_primary(self) -> None:
        rec = EntityRecord(
            artifact_id="A", artifact_type="t", name="n", version="", status="", domain="d", subdomain="s",
            path=Path("/x"), keywords=(), extra={}, content_text="", display_blocks={}, display_label="",
            display_alias="", specializations=("a", "b"),
        )
        assert rec.specialization == "a"

    def test_setting_only_the_scalar_derives_the_list(self) -> None:
        rec = EntityRecord(
            artifact_id="A", artifact_type="t", name="n", version="", status="", domain="d", subdomain="s",
            path=Path("/x"), keywords=(), extra={}, content_text="", display_blocks={}, display_label="",
            display_alias="", specialization="a",
        )
        assert rec.specializations == ("a",)

    def test_disagreeing_scalar_and_list_is_a_programming_error(self) -> None:
        with pytest.raises(ValueError, match="disagrees"):
            EntityRecord(
                artifact_id="A", artifact_type="t", name="n", version="", status="", domain="d", subdomain="s",
                path=Path("/x"), keywords=(), extra={}, content_text="", display_blocks={}, display_label="",
                display_alias="", specialization="a", specializations=("b", "a"),
            )

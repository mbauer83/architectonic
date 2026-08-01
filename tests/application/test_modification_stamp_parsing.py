"""The `last-updated` frontmatter stamp is read, normalized, and carried on every record kind.

Two things are pinned here. First, the normalization: PyYAML hands back a `date`/`datetime`
object for an *unquoted* stamp and a `str` for a quoted one, and `str()` on a tz-aware
datetime yields `2026-07-24 09:15:00+00:00` — a different shape from the canonical
`2026-07-24T09:15:00Z` the writer emits. Sorting a browse list mixes both shapes, so both
must normalize to one. Second, the breadth: all four browsable kinds expose the stamp, so a
"last modified" column cannot be present on entities and mysteriously blank on diagrams.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src.application.artifacts.parsing import (
    _canonical_stamp,
    parse_diagram,
    parse_document,
    parse_entity,
    parse_outgoing_file,
)

_DOMAINS = frozenset({"motivation", "application", "technology", "business", "strategy", "common"})


class TestCanonicalStamp:
    def test_canonical_string_passes_through(self) -> None:
        assert _canonical_stamp("2026-07-24T09:15:00Z") == "2026-07-24T09:15:00Z"

    def test_date_string_passes_through(self) -> None:
        assert _canonical_stamp("2026-07-24") == "2026-07-24"

    def test_date_object_renders_as_iso_date(self) -> None:
        assert _canonical_stamp(date(2026, 7, 24)) == "2026-07-24"

    def test_utc_datetime_renders_canonically(self) -> None:
        aware = datetime(2026, 7, 24, 9, 15, 0, tzinfo=timezone.utc)
        assert _canonical_stamp(aware) == "2026-07-24T09:15:00Z"

    def test_offset_datetime_is_converted_to_utc(self) -> None:
        aware = datetime(2026, 7, 24, 11, 15, 0, tzinfo=timezone(timedelta(hours=2)))
        assert _canonical_stamp(aware) == "2026-07-24T09:15:00Z"

    def test_naive_datetime_is_read_as_utc(self) -> None:
        assert _canonical_stamp(datetime(2026, 7, 24, 9, 15, 0)) == "2026-07-24T09:15:00Z"

    def test_empty_and_absent_are_no_stamp(self) -> None:
        assert _canonical_stamp("") is None
        assert _canonical_stamp(None) is None

    def test_date_sorts_before_a_later_datetime_lexically(self) -> None:
        # Mixed date/datetime stamps coexist until every repo is migrated; the browse sort
        # compares the raw strings, which only works if the ISO date is a lexical prefix.
        stamps = ["2026-07-24T09:15:00Z", "2026-07-23", "2026-07-24"]
        assert sorted(stamps) == ["2026-07-23", "2026-07-24", "2026-07-24T09:15:00Z"]


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestRecordBreadth:
    def test_entity_carries_the_stamp(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path / "motivation" / "requirement" / "REQ@1.abc.stamped.md",
            "---\nartifact-id: REQ@1.abc.stamped\nartifact-type: requirement\nname: Stamped\n"
            "version: 0.1.0\nstatus: draft\nlast-updated: '2026-07-24T09:15:00Z'\n---\n"
            "<!-- §content -->\n\n## Stamped\n\nBody.\n",
        )
        record = parse_entity(path, tmp_path, domain_names=_DOMAINS)
        assert record is not None
        assert record.last_updated == "2026-07-24T09:15:00Z"

    def test_entity_without_a_stamp_reads_as_unstamped(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path / "motivation" / "requirement" / "REQ@1.abc.bare.md",
            "---\nartifact-id: REQ@1.abc.bare\nartifact-type: requirement\nname: Bare\n---\nbody\n",
        )
        record = parse_entity(path, tmp_path, domain_names=_DOMAINS)
        assert record is not None
        assert record.last_updated is None

    def test_diagram_carries_the_stamp(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path / "D1.puml",
            "---\nartifact-id: ARC@1.abc.d1\nartifact-type: diagram\nname: D1\n"
            "diagram-type: archimate-motivation\nlast-updated: 2026-07-24\n---\n@startuml\n@enduml\n",
        )
        record = parse_diagram(path)
        assert record is not None
        assert record.last_updated == "2026-07-24"

    def test_document_carries_the_stamp(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path / "ADR@1.abc.decision.md",
            "---\nartifact-id: ADR@1.abc.decision\nartifact-type: document\ndoc-type: adr\n"
            "title: A Decision\nstatus: draft\nlast-updated: '2026-07-24T09:15:00Z'\n---\n\n## Context\n\nText.\n",
        )
        record = parse_document(path)
        assert record is not None
        assert record.last_updated == "2026-07-24T09:15:00Z"

    def test_every_connection_in_a_file_carries_that_file_stamp(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path / "REQ@1.abc.src.outgoing.md",
            "---\nsource-entity: REQ@1.abc.src\nversion: 0.1.0\nstatus: draft\n"
            "last-updated: '2026-07-24T09:15:00Z'\n---\n"
            "### realization → APP@1.abc.one\n\nFirst.\n\n### realization → APP@1.abc.two\n\nSecond.\n",
        )
        records = parse_outgoing_file(path)
        assert len(records) == 2
        assert {r.last_updated for r in records} == {"2026-07-24T09:15:00Z"}

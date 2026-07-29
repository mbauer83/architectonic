"""Tests for _promote_planning.py helper functions.

Covers: _parse_conn_full alternate format, _entity_frontmatter error paths,
_partition_selected GAR skipping, _collect_promotable_connections filtering.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from src.infrastructure.write.artifact_write._promote_planning import (
    _collect_promotable_connections,
    _entity_frontmatter,
    _parse_conn_full,
    _partition_selected,
)

# ---------------------------------------------------------------------------
# _parse_conn_full
# ---------------------------------------------------------------------------


class TestParseConnFull:
    def test_canonical_format_parsed(self) -> None:
        result = _parse_conn_full("REQ@1.A.a---REQ@2.B.b@@archimate-association")
        assert result is not None
        src, conn_type, tgt = result
        assert src == "REQ@1.A.a"
        assert conn_type == "archimate-association"
        assert tgt == "REQ@2.B.b"

    def test_arrow_format_parsed(self) -> None:
        result = _parse_conn_full("REQ@1.A.a archimate-association → REQ@2.B.b")
        assert result is not None
        src, conn_type, tgt = result
        assert src == "REQ@1.A.a"
        assert conn_type == "archimate-association"
        assert tgt == "REQ@2.B.b"

    def test_arrow_format_returns_none_when_no_space_parts(self) -> None:
        result = _parse_conn_full("single → REQ@2.B.b")
        assert result is None

    def test_returns_none_for_invalid_format(self) -> None:
        result = _parse_conn_full("no-separator-here")
        assert result is None

    def test_returns_none_for_empty_string(self) -> None:
        assert _parse_conn_full("") is None


# ---------------------------------------------------------------------------
# _entity_frontmatter
# ---------------------------------------------------------------------------


class TestEntityFrontmatter:
    def test_returns_empty_when_file_not_found(self) -> None:
        registry = MagicMock()
        registry.find_file_by_id = lambda eid: None
        result = _entity_frontmatter(registry, "REQ@9.ZZZ.not-found")
        assert result == {}

    def test_returns_empty_on_parse_exception(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.md"
        bad_file.write_text("not valid frontmatter at all")
        registry = MagicMock()
        registry.find_file_by_id = lambda eid: bad_file
        result = _entity_frontmatter(registry, "REQ@1.A.any")
        assert result == {}

    def test_returns_frontmatter_for_valid_file(self, tmp_path: Path) -> None:
        good_file = tmp_path / "entity.md"
        good_file.write_text(
            "---\nartifact-id: REQ@1.A.a\nname: Test\nartifact-type: requirement\n"
            "version: 0.1.0\nstatus: draft\nlast-updated: '2026-01-01'\n---\nbody\n"
        )
        registry = MagicMock()
        registry.find_file_by_id = lambda eid: good_file
        result = _entity_frontmatter(registry, "REQ@1.A.a")
        assert "name" in result
        assert result["name"] == "Test"


# ---------------------------------------------------------------------------
# _partition_selected
# ---------------------------------------------------------------------------


class TestPartitionSelected:
    def test_already_enterprise_partitioned(self) -> None:
        already, candidates = _partition_selected(
            ["ENT@1.A.a"],
            enterprise_ids={"ENT@1.A.a"},
            gar_ids=set(),
            warnings=[],
        )
        assert "ENT@1.A.a" in already
        assert candidates == []

    def test_gar_skipped_with_warning(self) -> None:
        warnings: list[str] = []
        already, candidates = _partition_selected(
            ["GAR@1.A.a"],
            enterprise_ids=set(),
            gar_ids={"GAR@1.A.a"},
            warnings=warnings,
        )
        assert already == []
        assert candidates == []
        assert any("GAR@1.A.a" in w for w in warnings)

    def test_fresh_candidate_partitioned(self) -> None:
        already, candidates = _partition_selected(
            ["REQ@1.A.a"],
            enterprise_ids=set(),
            gar_ids=set(),
            warnings=[],
        )
        assert already == []
        assert "REQ@1.A.a" in candidates


# ---------------------------------------------------------------------------
# _collect_promotable_connections
# ---------------------------------------------------------------------------


class TestCollectPromotableConnections:
    def test_matching_connection_collected(self) -> None:
        conn_id = "REQ@1.A.a---REQ@2.B.b@@archimate-association"
        registry = MagicMock()
        registry.connection_ids = lambda: [conn_id]
        result = _collect_promotable_connections(
            registry,
            promotable={"REQ@1.A.a"},
            selected_set={"REQ@1.A.a", "REQ@2.B.b"},
            explicit_connection_ids={conn_id},
        )
        assert conn_id in result

    def test_unparseable_connection_skipped(self) -> None:
        conn_id = "not-a-valid-connection"
        registry = MagicMock()
        registry.connection_ids = lambda: [conn_id]
        result = _collect_promotable_connections(
            registry,
            promotable={"REQ@1.A.a"},
            selected_set={"REQ@1.A.a"},
            explicit_connection_ids={conn_id},
        )
        assert result == []

    def test_source_not_promotable_excluded(self) -> None:
        conn_id = "REQ@1.A.a---REQ@2.B.b@@archimate-association"
        registry = MagicMock()
        registry.connection_ids = lambda: [conn_id]
        result = _collect_promotable_connections(
            registry,
            promotable={"REQ@99.X.x"},  # source not in promotable
            selected_set={"REQ@1.A.a", "REQ@2.B.b"},
            explicit_connection_ids={conn_id},
        )
        assert result == []

    def test_connection_not_in_explicit_set_excluded(self) -> None:
        conn_id = "REQ@1.A.a---REQ@2.B.b@@archimate-association"
        registry = MagicMock()
        registry.connection_ids = lambda: [conn_id]
        result = _collect_promotable_connections(
            registry,
            promotable={"REQ@1.A.a"},
            selected_set={"REQ@1.A.a", "REQ@2.B.b"},
            explicit_connection_ids=set(),  # not explicitly requested
        )
        assert result == []

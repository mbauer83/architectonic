"""Tests for artifact_query_cli — pure helpers and main() dispatch."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.ontology_representation.artifact_types import ConnectionRecord, DiagramRecord, EntityRecord
from src.infrastructure.cli.artifact_query_cli import (
    _format_connection_edge,
    _safe_items,
    bool_flag,
    flag,
    fmt_connection,
    fmt_diagram,
    fmt_entity,
    main,
    repo_from_args,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_entity(
    artifact_id: str = "REQ@1.ABC.my-req",
    name: str = "My Req",
    content_text: str = "",
    display_blocks: dict | None = None,
) -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type="requirement",
        name=name,
        version="0.1.0",
        status="active",
        domain="motivation",
        subdomain="requirement",
        path=Path("/tmp/test.md"),
        keywords=(),
        extra={},
        content_text=content_text,
        display_blocks=display_blocks or {},
        display_label=name,
        display_alias="REQ_ABC",
    )


def _make_connection(
    source: str = "REQ@1.ABC.source",
    target: str = "REQ@2.DEF.target",
    conn_type: str = "archimate-association",
    content_text: str = "",
) -> ConnectionRecord:
    artifact_id = f"{source}---{target}@@{conn_type}"
    return ConnectionRecord(
        artifact_id=artifact_id,
        source=source,
        target=target,
        conn_type=conn_type,
        version="0.1.0",
        status="active",
        path=Path("/tmp/src.outgoing.md"),
        extra={},
        content_text=content_text,
    )


def _make_diagram(
    artifact_id: str = "DIAG@1.XYZ.my-diagram",
    name: str = "My Diagram",
) -> DiagramRecord:
    return DiagramRecord(
        artifact_id=artifact_id,
        artifact_type="diagram",
        name=name,
        diagram_type="component",
        version="0.1.0",
        status="active",
        path=Path("/tmp/my-diagram.md"),
        extra={},
    )


def _entity_md(artifact_id: str, name: str) -> str:
    slug = artifact_id.split(".")[-1]
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: requirement
name: "{name}"
version: 0.1.0
status: active
last-updated: '2026-01-01'
---

<!-- §content -->

## {name}

Test entity.

## Properties

| Attribute | Value |
|---|---|
| (none) | (none) |

<!-- §display -->

### archimate

```yaml
domain: Motivation
element-type: Requirement
label: "{name}"
alias: REQ_{slug}
```
"""


def _outgoing_md(source: str, target: str, conn_type: str = "archimate-association") -> str:
    return f"""\
---
artifact-id: {source}
version: 0.1.0
status: active
last-updated: '2026-01-01'
---

<!-- §connections -->

### {conn_type} → {target}

Description.
"""


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-CLI" / "architecture-repository"
    root.mkdir(parents=True)
    return root


@pytest.fixture()
def populated_root(repo_root: Path) -> Path:
    model_dir = repo_root / "model" / "motivation" / "requirement"
    model_dir.mkdir(parents=True)
    src_id = "REQ@1000000001.SrcCLI.source-cli"
    tgt_id = "REQ@1000000002.TgtCLI.target-cli"
    (model_dir / f"{src_id}.md").write_text(_entity_md(src_id, "Source CLI"))
    (model_dir / f"{tgt_id}.md").write_text(_entity_md(tgt_id, "Target CLI"))
    (model_dir / f"{src_id}.outgoing.md").write_text(_outgoing_md(src_id, tgt_id))
    return repo_root


# ── flag / bool_flag ──────────────────────────────────────────────────────────


class TestFlag:
    def test_extracts_value(self) -> None:
        val, rest = flag(["--type", "foo", "bar"], "--type")
        assert val == "foo"
        assert rest == ["bar"]

    def test_absent_returns_none(self) -> None:
        val, rest = flag(["bar"], "--type")
        assert val is None
        assert rest == ["bar"]

    def test_flag_at_end_returns_none_value(self) -> None:
        val, rest = flag(["--type"], "--type")
        assert val is None
        assert rest == []

    def test_multiple_flags_only_removes_first(self) -> None:
        val, rest = flag(["--type", "x", "extra"], "--type")
        assert val == "x"
        assert rest == ["extra"]


class TestBoolFlag:
    def test_present(self) -> None:
        present, rest = bool_flag(["--verbose", "x"], "--verbose")
        assert present is True
        assert rest == ["x"]

    def test_absent(self) -> None:
        present, rest = bool_flag(["x"], "--verbose")
        assert present is False
        assert rest == ["x"]


# ── _safe_items ───────────────────────────────────────────────────────────────


class TestSafeItems:
    def test_returns_pairs_from_dict(self) -> None:
        result = _safe_items({"a": 3, "b": 1})
        assert set(result) == {("a", 3), ("b", 1)}

    def test_non_dict_returns_empty(self) -> None:
        assert _safe_items("hello") == []
        assert _safe_items(None) == []
        assert _safe_items(42) == []

    def test_empty_dict(self) -> None:
        assert _safe_items({}) == []


# ── _format_connection_edge ───────────────────────────────────────────────────


class TestFormatConnectionEdge:
    def test_outbound_direction(self) -> None:
        src = "REQ@1.ABC.source"
        tgt = "REQ@2.DEF.target"
        conn = _make_connection(source=src, target=tgt)
        result = _format_connection_edge(conn, entity_id=src)
        assert "OUT" in result
        assert tgt in result

    def test_inbound_direction(self) -> None:
        src = "REQ@1.ABC.source"
        tgt = "REQ@2.DEF.target"
        conn = _make_connection(source=src, target=tgt)
        result = _format_connection_edge(conn, entity_id=tgt)
        assert "IN " in result
        assert src in result


# ── formatters ────────────────────────────────────────────────────────────────


class TestFmtEntity:
    def test_basic(self) -> None:
        rec = _make_entity()
        out = fmt_entity(rec)
        assert "REQ@1.ABC.my-req" in out
        assert "My Req" in out

    def test_verbose_with_content(self) -> None:
        rec = _make_entity(content_text="## Summary\n\nSome context here for testing.")
        out = fmt_entity(rec, verbose=True)
        assert "Some context here" in out

    def test_verbose_with_display_blocks(self) -> None:
        rec = _make_entity(display_blocks={"archimate": "domain: Motivation\nelement: Req"})
        out = fmt_entity(rec, verbose=True)
        assert "archimate" in out


class TestFmtConnection:
    def test_basic(self) -> None:
        rec = _make_connection()
        out = fmt_connection(rec)
        assert "archimate-association" in out

    def test_verbose_with_content(self) -> None:
        rec = _make_connection(content_text="Connection description text.")
        out = fmt_connection(rec, verbose=True)
        assert "Connection description text" in out


class TestFmtDiagram:
    def test_basic(self) -> None:
        rec = _make_diagram()
        out = fmt_diagram(rec)
        assert "DIAG@1.XYZ.my-diagram" in out
        assert "My Diagram" in out


# ── repo_from_args ────────────────────────────────────────────────────────────


class TestRepoFromArgs:
    def test_with_explicit_repo_flag(self, tmp_path: Path) -> None:
        repo, remaining = repo_from_args(["--repo", str(tmp_path), "extra"])
        assert repo == tmp_path
        assert remaining == ["extra"]

    def test_repo_flag_with_no_remaining(self, tmp_path: Path) -> None:
        repo, remaining = repo_from_args(["--repo", str(tmp_path)])
        assert repo == tmp_path
        assert remaining == []


# ── main() dispatch ───────────────────────────────────────────────────────────


class TestMain:
    def test_empty_args_shows_usage(self, capsys: pytest.CaptureFixture) -> None:
        assert main(argv=[]) == 0
        assert "Usage" in capsys.readouterr().out

    def test_help_flag(self, capsys: pytest.CaptureFixture) -> None:
        assert main(argv=["-h"]) == 0
        assert "Usage" in capsys.readouterr().out

    def test_double_help_flag(self, capsys: pytest.CaptureFixture) -> None:
        assert main(argv=["--help"]) == 0

    def test_nonexistent_repo(self) -> None:
        assert main(argv=["stats", "--repo", "/nonexistent/xyz/abc"]) == 1

    def test_unknown_subcommand(self, repo_root: Path) -> None:
        assert main(argv=["nosuchcmd", "--repo", str(repo_root)]) == 1

    def test_stats_empty_repo(self, repo_root: Path) -> None:
        assert main(argv=["stats", "--repo", str(repo_root)]) == 0

    def test_entities_empty_repo(self, repo_root: Path) -> None:
        assert main(argv=["entities", "--repo", str(repo_root)]) == 0

    def test_entities_with_domain_filter(self, populated_root: Path) -> None:
        assert main(argv=["entities", "--repo", str(populated_root), "--domain", "motivation"]) == 0

    def test_entities_verbose(self, populated_root: Path) -> None:
        assert main(argv=["entities", "--repo", str(populated_root), "--verbose"]) == 0

    def test_connections_empty_repo(self, repo_root: Path) -> None:
        assert main(argv=["connections", "--repo", str(repo_root)]) == 0

    def test_connections_with_type_filter(self, populated_root: Path) -> None:
        rc = main(argv=["connections", "--repo", str(populated_root), "--type", "archimate-association"])
        assert rc == 0

    def test_connections_verbose(self, populated_root: Path) -> None:
        assert main(argv=["connections", "--repo", str(populated_root), "--verbose"]) == 0

    def test_diagrams_empty_repo(self, repo_root: Path) -> None:
        assert main(argv=["diagrams", "--repo", str(repo_root)]) == 0

    def test_get_no_id(self, repo_root: Path) -> None:
        assert main(argv=["get", "--repo", str(repo_root)]) == 1

    def test_get_not_found(self, repo_root: Path) -> None:
        assert main(argv=["get", "--repo", str(repo_root), "REQ@1.XYZ.no-such"]) == 1

    def test_get_found_entity(self, populated_root: Path) -> None:
        rc = main(argv=["get", "--repo", str(populated_root), "REQ@1000000001.SrcCLI.source-cli"])
        assert rc == 0

    def test_graph_no_id(self, repo_root: Path) -> None:
        assert main(argv=["graph", "--repo", str(repo_root)]) == 1

    def test_graph_not_found(self, repo_root: Path) -> None:
        assert main(argv=["graph", "--repo", str(repo_root), "REQ@1.XYZ.no-such"]) == 1

    def test_graph_found(self, populated_root: Path) -> None:
        rc = main(argv=["graph", "--repo", str(populated_root), "REQ@1000000001.SrcCLI.source-cli"])
        assert rc == 0

    def test_graph_found_multihop(self, populated_root: Path) -> None:
        rc = main(argv=[
            "graph", "--repo", str(populated_root),
            "--hops", "2", "REQ@1000000001.SrcCLI.source-cli",
        ])
        assert rc == 0

    def test_search_no_query(self, repo_root: Path) -> None:
        assert main(argv=["search", "--repo", str(repo_root)]) == 1

    def test_search_with_query(self, repo_root: Path) -> None:
        assert main(argv=["search", "--repo", str(repo_root), "any", "text"]) == 0

    def test_search_with_limit(self, populated_root: Path) -> None:
        rc = main(argv=["search", "--repo", str(populated_root), "--limit", "5", "Source"])
        assert rc == 0

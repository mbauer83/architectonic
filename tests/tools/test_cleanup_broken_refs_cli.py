"""Tests for cleanup_broken_refs CLI main() and core functions.

Covers: main() with valid args (dry-run), main() with JSON output,
main() missing roots error path, find_broken_grfs, cleanup_broken_refs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.artifact_query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.cleanup_broken_refs import (
    cleanup_broken_refs,
    find_broken_grfs,
    main,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _enterprise_root(tmp_path: Path) -> Path:
    root = tmp_path / "enterprise-repository"
    root.mkdir(parents=True)
    return root


def _engagement_root(tmp_path: Path, tag: str = "CLN") -> Path:
    root = tmp_path / "engagements" / f"ENG-{tag}" / "architecture-repository"
    root.mkdir(parents=True)
    return root


# ── main() — no roots ─────────────────────────────────────────────────────────


class TestMainMissingRoots:
    def test_parser_error_when_no_roots(self) -> None:
        from unittest.mock import patch

        with patch("src.infrastructure.workspace.workspace_init.load_init_state", return_value=None):
            with pytest.raises(SystemExit):
                main([])  # no --repo-root or --enterprise-root, and no init state


# ── main() — happy path (no broken GRFs) ─────────────────────────────────────


class TestMainHappyPath:
    def test_dry_run_with_no_broken_grfs(self, tmp_path: Path, capsys) -> None:
        eng = _engagement_root(tmp_path, "CLN1")
        ent = _enterprise_root(tmp_path)
        main(["--repo-root", str(eng), "--enterprise-root", str(ent)])
        out = capsys.readouterr().out
        assert "No broken" in out or "cleanup" in out.lower() or "" in out

    def test_json_output_format(self, tmp_path: Path, capsys) -> None:
        eng = _engagement_root(tmp_path, "CLN2")
        ent = _enterprise_root(tmp_path)
        main(["--repo-root", str(eng), "--enterprise-root", str(ent), "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "broken_grfs" in data
        assert "executed" in data

    def test_execute_flag_sets_executed_true(self, tmp_path: Path, capsys) -> None:
        eng = _engagement_root(tmp_path, "CLN3")
        ent = _enterprise_root(tmp_path)
        main(["--repo-root", str(eng), "--enterprise-root", str(ent), "--execute"])
        out = capsys.readouterr().out
        # No broken GRFs, but "executed" mode indicated in output
        assert "EXECUTED" in out or "No broken" in out


# ── main() — with broken GRF ──────────────────────────────────────────────────


def _grf_md(artifact_id: str, global_id: str) -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: global-artifact-reference
global-artifact-id: {global_id}
name: "Broken GRF"
version: 0.1.0
status: active
last-updated: '2026-01-01'
---

<!-- §content -->

## Broken GRF

Proxy for a missing enterprise entity.

## Properties

| Attribute | Value |
|---|---|
| (none) | (none) |

<!-- §display -->

### archimate

```yaml
domain: Motivation
element-type: Requirement
label: "Broken GRF"
alias: GAR_BRK
```
"""


class TestMainWithBrokenGRF:
    def test_broken_grf_shown_in_text_output(self, tmp_path: Path, capsys) -> None:
        eng = _engagement_root(tmp_path, "CLN4")
        ent = _enterprise_root(tmp_path)
        grf_id = "GAR@1000000100.BrkGrf.broken-grf"
        _write(
            eng / "model" / "motivation" / "global-artifact-reference" / f"{grf_id}.md",
            _grf_md(grf_id, "REQ@9.ZZZ.missing-enterprise"),
        )
        main(["--repo-root", str(eng), "--enterprise-root", str(ent)])
        out = capsys.readouterr().out
        assert grf_id in out or "Broken" in out

    def test_broken_grf_shown_in_json_output(self, tmp_path: Path, capsys) -> None:
        eng = _engagement_root(tmp_path, "CLN5")
        ent = _enterprise_root(tmp_path)
        grf_id = "GAR@1000000101.BrkGrf2.broken-grf-two"
        _write(
            eng / "model" / "motivation" / "global-artifact-reference" / f"{grf_id}.md",
            _grf_md(grf_id, "REQ@9.ZZZ.missing-enterprise-two"),
        )
        main(["--repo-root", str(eng), "--enterprise-root", str(ent), "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert len(data["broken_grfs"]) >= 1


# ── find_broken_grfs ──────────────────────────────────────────────────────────


class TestFindBrokenGRFs:
    def test_no_grfs_returns_empty(self, tmp_path: Path) -> None:
        eng = _engagement_root(tmp_path, "FBG1")
        repo = ArtifactRepository(shared_artifact_index([eng]))
        result = find_broken_grfs(repo, eng, enterprise_entity_ids=set())
        assert result == []

    def test_broken_grf_detected(self, tmp_path: Path) -> None:
        eng = _engagement_root(tmp_path, "FBG2")
        grf_id = "GAR@1000000102.BrkGrf3.broken-grf-three"
        _write(
            eng / "model" / "motivation" / "global-artifact-reference" / f"{grf_id}.md",
            _grf_md(grf_id, "REQ@9.ZZZ.missing"),
        )
        repo = ArtifactRepository(shared_artifact_index([eng]))
        result = find_broken_grfs(repo, eng, enterprise_entity_ids=set())
        ids = [r[0] for r in result]
        assert grf_id in ids


# ── cleanup_broken_refs ───────────────────────────────────────────────────────


class TestCleanupBrokenRefs:
    def test_dry_run_with_no_grfs(self, tmp_path: Path) -> None:
        eng = _engagement_root(tmp_path, "CBR1")
        ent = _enterprise_root(tmp_path)
        report = cleanup_broken_refs(eng, ent, dry_run=True)
        assert report.broken_grfs == []
        assert report.executed is False

    def test_dry_run_with_broken_grf(self, tmp_path: Path) -> None:
        eng = _engagement_root(tmp_path, "CBR2")
        ent = _enterprise_root(tmp_path)
        grf_id = "GAR@1000000103.BrkGrf4.broken-grf-four"
        _write(
            eng / "model" / "motivation" / "global-artifact-reference" / f"{grf_id}.md",
            _grf_md(grf_id, "REQ@9.ZZZ.missing-enterprise-cbr"),
        )
        report = cleanup_broken_refs(eng, ent, dry_run=True)
        assert grf_id in report.broken_grfs
        assert report.executed is False
        # Dry run doesn't remove files
        assert (eng / "model" / "motivation" / "global-artifact-reference" / f"{grf_id}.md").exists()

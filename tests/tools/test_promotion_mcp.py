"""Tests for the model_promote_to_enterprise MCP tool.

Covers: dry-run plan output, conflict detection, execution with GRF replacement,
exclude params, and rollback on verification failure.
"""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@lru_cache(maxsize=1)
def _all_entity_types() -> dict:
    from src.infrastructure.app_bootstrap import build_module_registry  # noqa: PLC0415

    return {str(k): v for k, v in build_module_registry().all_entity_types().items()}


def _entity_md(artifact_id: str, artifact_type: str, name: str) -> str:
    prefix = artifact_id.split("@")[0]
    rand = artifact_id.split(".")[1] if "." in artifact_id else "XXXXXX"
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: {artifact_type}
name: "{name}"
version: 0.1.0
status: active
last-updated: '2026-04-17'
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
alias: {prefix}_{rand}
```
"""


def _git_init(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    (path / ".gitkeep").write_text("")
    subprocess.run(["git", "add", ".gitkeep"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


@pytest.fixture()
def engagement_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    _git_init(root)
    (root / "model").mkdir(parents=True, exist_ok=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture()
def enterprise_root(tmp_path: Path) -> Path:
    root = tmp_path / "enterprise-repository"
    _git_init(root)
    (root / "model").mkdir(parents=True, exist_ok=True)
    return root


def _make_entity(root: Path, artifact_id: str, artifact_type: str, name: str) -> None:
    info = _all_entity_types()[artifact_type]
    path = root / "model" / Path(*info.hierarchy) / f"{artifact_id}.md"
    _write(path, _entity_md(artifact_id, artifact_type, name))


# ---------------------------------------------------------------------------
# Dry-run plan
# ---------------------------------------------------------------------------


class TestPromotionDryRun:
    def test_dry_run_returns_entities_to_add(self, engagement_root: Path, enterprise_root: Path) -> None:
        eng_id = "REQ@1000000001.EngAaa.eng-req"
        _make_entity(engagement_root, eng_id, "requirement", "Eng Req")

        result = mcp.artifact_promote_to_enterprise(
            entity_id=eng_id,
            dry_run=True,
            repo_root=str(engagement_root),
            enterprise_root=str(enterprise_root),
        )

        assert result["dry_run"] is True
        assert eng_id in result["entities_to_add"]
        assert not result.get("executed")

    def test_dry_run_detects_conflict(self, engagement_root: Path, enterprise_root: Path) -> None:
        eng_id = "REQ@1000000001.EngAaa.shared-req"
        ent_id = "REQ@2000000001.EntBbb.shared-req"
        _make_entity(engagement_root, eng_id, "requirement", "Shared Req")
        _make_entity(enterprise_root, ent_id, "requirement", "Shared Req")  # same name → conflict

        result = mcp.artifact_promote_to_enterprise(
            entity_id=eng_id,
            dry_run=True,
            repo_root=str(engagement_root),
            enterprise_root=str(enterprise_root),
        )

        assert any(c["engagement_id"] == eng_id for c in result["conflicts"])

    def test_explicit_enterprise_selection_is_reported(self, engagement_root: Path, enterprise_root: Path) -> None:
        eng_id = "REQ@1000000010.EngAaa.root-req"
        ent_id = "REQ@2000000001.EntBbb.global-req"
        _make_entity(engagement_root, eng_id, "requirement", "Root Req")
        _make_entity(enterprise_root, ent_id, "requirement", "Global Req")

        result = mcp.artifact_promote_to_enterprise(
            entity_id=eng_id,
            entity_ids=[eng_id, ent_id],
            dry_run=True,
            repo_root=str(engagement_root),
            enterprise_root=str(enterprise_root),
        )
        assert ent_id in result["already_in_enterprise"]

    def test_dry_run_reports_missing_dependencies(self, engagement_root: Path, enterprise_root: Path) -> None:
        eng_id = "REQ@1000000031.EngMdp.dep-req"
        _make_entity(engagement_root, eng_id, "requirement", "Dep Req")
        result = mcp.artifact_promote_to_enterprise(
            entity_id=eng_id,
            dry_run=True,
            repo_root=str(engagement_root),
            enterprise_root=str(enterprise_root),
        )
        assert result["missing_dependencies"] == []

    def test_invalid_viewpoint_resolution_value_is_rejected(
        self, engagement_root: Path, enterprise_root: Path
    ) -> None:
        eng_id = "REQ@1000000032.EngVpr.vp-req"
        _make_entity(engagement_root, eng_id, "requirement", "Vp Req")
        with pytest.raises(ValueError, match="viewpoint_resolutions"):
            mcp.artifact_promote_to_enterprise(
                entity_id=eng_id,
                dry_run=True,
                viewpoint_resolutions={"some-viewpoint": "overwrite"},
                repo_root=str(engagement_root),
                enterprise_root=str(enterprise_root),
            )

    def test_exclude_entities_prunes_plan(self, engagement_root: Path, enterprise_root: Path) -> None:
        eng_id1 = "REQ@1000000001.EngAaa.req1"
        eng_id2 = "REQ@1000000002.EngBbb.req2"
        _make_entity(engagement_root, eng_id1, "requirement", "Req 1")
        _make_entity(engagement_root, eng_id2, "requirement", "Req 2")
        result = mcp.artifact_promote_to_enterprise(
            entity_id=eng_id1,
            entity_ids=[eng_id1, eng_id2],
            exclude_entities=[eng_id2],
            dry_run=True,
            repo_root=str(engagement_root),
            enterprise_root=str(enterprise_root),
        )
        assert eng_id1 in result["entities_to_add"]
        assert eng_id2 not in result["entities_to_add"]


# ---------------------------------------------------------------------------
# Live execution
# ---------------------------------------------------------------------------


class TestPromotionExecute:
    def test_entity_copied_to_enterprise(self, engagement_root: Path, enterprise_root: Path) -> None:
        eng_id = "REQ@1000000001.EngAaa.live-req"
        _make_entity(engagement_root, eng_id, "requirement", "Live Req")

        result = mcp.artifact_promote_to_enterprise(
            entity_id=eng_id,
            dry_run=False,
            repo_root=str(engagement_root),
            enterprise_root=str(enterprise_root),
        )

        assert result["executed"] is True
        assert not result["rolled_back"]
        ent_file = enterprise_root / "model" / "motivation" / "requirement" / f"{eng_id}.md"
        assert ent_file.exists()

    def test_engagement_entity_replaced_by_grf(self, engagement_root: Path, enterprise_root: Path) -> None:
        eng_id = "REQ@1000000002.EngBbb.to-replace"
        _make_entity(engagement_root, eng_id, "requirement", "To Replace")

        orig_path = engagement_root / "model" / "motivation" / "requirement" / f"{eng_id}.md"
        assert orig_path.exists()

        result = mcp.artifact_promote_to_enterprise(
            entity_id=eng_id,
            dry_run=False,
            repo_root=str(engagement_root),
            enterprise_root=str(enterprise_root),
        )

        assert result["executed"] is True
        assert not orig_path.exists(), "Original entity should be replaced by GRF"
        grf_dir = engagement_root / "model" / "common" / "global-artifact-reference"
        grfs = list(grf_dir.rglob("GAR@*.md")) if grf_dir.exists() else []
        assert grfs, "A GAR proxy should have been created"
        assert any(eng_id in f.read_text() for f in grfs)

    def test_accept_enterprise_conflict_resolution(self, engagement_root: Path, enterprise_root: Path) -> None:
        eng_id = "REQ@1000000003.EngCcc.conflict-req"
        ent_id = "REQ@2000000003.EntDdd.conflict-req"
        _make_entity(engagement_root, eng_id, "requirement", "Conflict Req")
        _make_entity(enterprise_root, ent_id, "requirement", "Conflict Req")

        result = mcp.artifact_promote_to_enterprise(
            entity_id=eng_id,
            dry_run=False,
            conflict_resolutions=[
                {
                    "engagement_id": eng_id,
                    "strategy": "accept_enterprise",
                }
            ],
            repo_root=str(engagement_root),
            enterprise_root=str(enterprise_root),
        )

        assert result["executed"] is True
        # Enterprise file should be unchanged
        ent_content = (enterprise_root / "model" / "motivation" / "requirement" / f"{ent_id}.md").read_text()
        assert ent_id in ent_content

    def test_grf_targets_rewritten_in_enterprise_outgoing(self, engagement_root: Path, enterprise_root: Path) -> None:
        eng_id = "REQ@1000000004.EngEee.main-req"
        grf_id = "GAR@1000000005.GrfFff.grf-ref"
        glo_id = "REQ@2000000005.EntGgg.global-req"

        _make_entity(engagement_root, eng_id, "requirement", "Main Req")
        _make_entity(enterprise_root, glo_id, "requirement", "Global Req")
        # GAR proxy
        grf_path = engagement_root / "model" / "common" / "global-artifact-reference" / f"{grf_id}.md"
        _write(
            grf_path,
            f"""\
---
artifact-id: {grf_id}
artifact-type: global-artifact-reference
name: "Global Req Ref"
version: 0.1.0
status: active
global-artifact-id: {glo_id}
global-artifact-type: entity
last-updated: '2026-04-17'
---

<!-- §content -->

## Global Req Ref

<!-- §display -->

### archimate

```yaml
domain: ""
element-type: ""
label: "Global Req Ref"
alias: GAR_GrfFff
```
""",
        )
        outgoing_path = engagement_root / "model" / "motivation" / "requirement" / f"{eng_id}.outgoing.md"
        _write(
            outgoing_path,
            f"""\
---
source-entity: {eng_id}
version: 0.1.0
status: active
last-updated: '2026-04-17'
---

<!-- §connections -->

### archimate-association → {grf_id}
""",
        )

        result = mcp.artifact_promote_to_enterprise(
            entity_id=eng_id,
            dry_run=False,
            repo_root=str(engagement_root),
            enterprise_root=str(enterprise_root),
        )

        assert result["executed"] is True
        ent_outgoing = enterprise_root / "model" / "motivation" / "requirement" / f"{eng_id}.outgoing.md"
        assert ent_outgoing.exists()
        content = ent_outgoing.read_text()
        assert grf_id not in content, "GRF should be rewritten to global entity"
        assert glo_id in content

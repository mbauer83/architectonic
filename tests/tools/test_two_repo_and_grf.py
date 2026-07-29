"""Behavioural tests for the two-tiered repo system and global-artifact-reference (GAR).

Covers:
- ArtifactRepository loading from both engagement and enterprise repos
- is_global classification via path
- GAR creation / reuse (ensure_global_artifact_reference)
- model_add_connection transparent GAR routing for global-entity targets
- Verifier rules E140 / E141 / W141 for GAR entities
- Promotion plan: excludes GARs and respects explicit selection
- Promotion execute: rewrites GAR targets in outgoing files
- Promotion execute: replaces promoted engagement entities with GARs
- Promotion execute: updates engagement outgoing references after replacement
- Promotion execute: handles pre-existing GARs correctly (idempotent)
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest

from src.application.artifact_query import ArtifactRepository
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp import mcp_artifact_server as mcp_tools


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry  # noqa: PLC0415

    return build_runtime_catalogs(get_module_registry())

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _use_workspace_roots(
    monkeypatch: pytest.MonkeyPatch,
    engagement_root: Path,
    enterprise_root: Path,
) -> None:
    monkeypatch.setattr(
        "src.infrastructure.mcp.artifact_mcp.context.resolve_workspace_repo_roots",
        lambda _start=None: (engagement_root.resolve(), enterprise_root.resolve()),
    )


def _entity_md(
    artifact_id: str,
    artifact_type: str,
    name: str,
    *,
    extra_frontmatter: str = "",
) -> str:
    prefix = artifact_id.split("@")[0] if "@" in artifact_id else "ENT"
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: {artifact_type}
name: "{name}"
version: 0.1.0
status: active
last-updated: '2026-04-17'{extra_frontmatter}
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
alias: {prefix}_{artifact_id.split(".")[1] if "." in artifact_id else "TEST"}
```
"""


def _grf_md(artifact_id: str, name: str, global_entity_id: str) -> str:
    rand = artifact_id.split(".")[1] if "." in artifact_id else "XXXXXX"
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: global-artifact-reference
name: "{name}"
version: 0.1.0
status: active
global-artifact-id: {global_entity_id}
global-artifact-type: entity
last-updated: '2026-04-17'
---

<!-- §content -->

## {name}

Engagement-repo proxy for promoted entity `{global_entity_id}`.

<!-- §display -->

### archimate

```yaml
domain: ""
element-type: ""
label: "{name}"
alias: GAR_{rand}
```
"""


def _outgoing_md(source_entity: str, connections: list[tuple[str, str]]) -> str:
    """connections: list of (conn_type, target_id)"""
    sections = "\n".join(f"### {ctype} → {tid}\n" for ctype, tid in connections)
    return f"""\
---
source-entity: {source_entity}
version: 0.1.0
status: active
last-updated: '2026-04-17'
---

<!-- §connections -->

{sections}
"""


@pytest.fixture()
def engagement_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-TEST" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


@pytest.fixture()
def enterprise_root(tmp_path: Path) -> Path:
    root = tmp_path / "enterprise-repository"
    (root / "model").mkdir(parents=True)
    return root


# ---------------------------------------------------------------------------
# Two-repo loading
# ---------------------------------------------------------------------------


class TestTwoRepoLoading:
    def test_entities_from_both_repos_visible(self, engagement_root: Path, enterprise_root: Path) -> None:
        _write(
            engagement_root / "model" / "motivation" / "requirements" / "REQ@1000000000.EngAAA.eng-req.md",
            _entity_md("REQ@1000000000.EngAAA.eng-req", "requirement", "Eng Req"),
        )
        _write(
            enterprise_root / "model" / "motivation" / "requirements" / "REQ@2000000000.GloAAA.global-req.md",
            _entity_md("REQ@2000000000.GloAAA.global-req", "requirement", "Global Req"),
        )

        repo = ArtifactRepository(shared_artifact_index([engagement_root, enterprise_root]))
        ids = {e.artifact_id for e in repo.list_entities()}
        assert "REQ@1000000000.EngAAA.eng-req" in ids
        assert "REQ@2000000000.GloAAA.global-req" in ids

    def test_is_global_via_path(self, engagement_root: Path, enterprise_root: Path) -> None:
        eng_file = engagement_root / "model" / "motivation" / "requirements" / "REQ@1000000000.EngAAA.eng-req.md"
        ent_file = enterprise_root / "model" / "motivation" / "requirements" / "REQ@2000000000.GloAAA.global-req.md"
        _write(eng_file, _entity_md("REQ@1000000000.EngAAA.eng-req", "requirement", "E"))
        _write(ent_file, _entity_md("REQ@2000000000.GloAAA.global-req", "requirement", "G"))

        repo = ArtifactRepository(shared_artifact_index([engagement_root, enterprise_root]))
        eng_rec = repo.get_entity("REQ@1000000000.EngAAA.eng-req")
        ent_rec = repo.get_entity("REQ@2000000000.GloAAA.global-req")
        assert eng_rec is not None and ent_rec is not None
        assert not eng_rec.path.is_relative_to(enterprise_root)
        assert ent_rec.path.is_relative_to(enterprise_root)

    def test_registry_scope_classification(self, engagement_root: Path, enterprise_root: Path) -> None:
        _write(
            engagement_root / "model" / "motivation" / "requirements" / "REQ@1000000000.EngAAA.eng-req.md",
            _entity_md("REQ@1000000000.EngAAA.eng-req", "requirement", "E"),
        )
        _write(
            enterprise_root / "model" / "motivation" / "requirements" / "REQ@2000000000.GloAAA.global-req.md",
            _entity_md("REQ@2000000000.GloAAA.global-req", "requirement", "G"),
        )
        registry = ArtifactRegistry(shared_artifact_index([engagement_root, enterprise_root]))
        assert registry.scope_of_entity("REQ@1000000000.EngAAA.eng-req") == "engagement"
        assert registry.scope_of_entity("REQ@2000000000.GloAAA.global-req") == "enterprise"


# ---------------------------------------------------------------------------
# GAR creation
# ---------------------------------------------------------------------------


class TestGrfCreation:
    def test_ensure_creates_new_grf(self, engagement_root: Path, enterprise_root: Path) -> None:
        from src.infrastructure.write.artifact_write.global_artifact_reference import ensure_global_artifact_reference

        repo = ArtifactRepository(shared_artifact_index(engagement_root))
        result = ensure_global_artifact_reference(
            engagement_repo=repo,
            engagement_root=engagement_root,
            verifier=ArtifactVerifier(None, catalogs=_catalogs()),
            clear_repo_caches=lambda _: None,
            global_artifact_id="REQ@2000000000.GloAAA.global-req",
            global_artifact_name="Global Req",
            global_artifact_type="entity",
            dry_run=False,
        )
        assert result.wrote is True
        assert result.artifact_id.startswith("GAR@")
        assert result.path.exists()
        content = result.path.read_text()
        assert "global-artifact-id: REQ@2000000000.GloAAA.global-req" in content

    def test_ensure_reuses_existing_grf(self, engagement_root: Path) -> None:
        from src.infrastructure.artifact_index import notify_paths_changed
        from src.infrastructure.write.artifact_write.global_artifact_reference import ensure_global_artifact_reference

        def _notify(path: Path | list[Path]) -> None:
            notify_paths_changed(path if isinstance(path, list) else [path])

        global_id = "REQ@2000000000.GloAAA.global-req"
        repo = ArtifactRepository(shared_artifact_index(engagement_root))

        r1 = ensure_global_artifact_reference(
            engagement_repo=repo,
            engagement_root=engagement_root,
            verifier=ArtifactVerifier(None, catalogs=_catalogs()),
            clear_repo_caches=_notify,
            global_artifact_id=global_id,
            global_artifact_name="Global Req",
            global_artifact_type="entity",
            dry_run=False,
        )
        assert r1.wrote is True

        repo2 = ArtifactRepository(shared_artifact_index(engagement_root))
        r2 = ensure_global_artifact_reference(
            engagement_repo=repo2,
            engagement_root=engagement_root,
            verifier=ArtifactVerifier(None, catalogs=_catalogs()),
            clear_repo_caches=_notify,
            global_artifact_id=global_id,
            global_artifact_name="Global Req",
            global_artifact_type="entity",
            dry_run=False,
        )
        assert r2.wrote is False
        assert r2.artifact_id == r1.artifact_id

    def test_build_grf_map(self, engagement_root: Path) -> None:
        from src.infrastructure.write.artifact_write.global_artifact_reference import build_gar_map

        gar_dir = engagement_root / "model" / "common" / "global-artifact-reference"
        _write(
            gar_dir / "GAR@1000000001.AbcDef.global-req.md",
            _grf_md(
                "GAR@1000000001.AbcDef.global-req",
                "Global Req",
                "REQ@2000000000.GloAAA.global-req",
            ),
        )
        repo = ArtifactRepository(shared_artifact_index(engagement_root))
        gar_map = build_gar_map(repo)
        assert gar_map["GAR@1000000001.AbcDef.global-req"] == "REQ@2000000000.GloAAA.global-req"


# ---------------------------------------------------------------------------
# Verifier GAR rules
# ---------------------------------------------------------------------------


class TestGrfVerifierRules:
    def test_grf_valid_with_enterprise_registry(
        self, engagement_root: Path, enterprise_root: Path, tmp_path: Path
    ) -> None:
        global_id = "REQ@2000000000.GloAAA.global-req"
        _write(
            enterprise_root / "model" / "motivation" / "requirements" / f"{global_id}.md",
            _entity_md(global_id, "requirement", "Global Req"),
        )
        gar_id = "GAR@1000000001.AbcDef.global-req"
        gar_path = engagement_root / "model" / "common" / "global-artifact-reference" / f"{gar_id}.md"
        _write(gar_path, _grf_md(gar_id, "Global Req", global_id))

        registry = ArtifactRegistry(shared_artifact_index([engagement_root, enterprise_root]))
        verifier = ArtifactVerifier(registry, catalogs=_catalogs())
        result = verifier.verify_entity_file(gar_path)
        errors = [i for i in result.issues if i.severity == "error"]
        assert not errors, [i.message for i in errors]

    def test_grf_e140_missing_global_entity_id(self, engagement_root: Path) -> None:
        gar_id = "GAR@1000000001.AbcDef.bad-gar"
        gar_path = engagement_root / "model" / "common" / "global-artifact-reference" / f"{gar_id}.md"
        # Write a GAR without global-artifact-id
        _write(gar_path, _entity_md(gar_id, "global-artifact-reference", "Bad GAR"))

        verifier = ArtifactVerifier(None, catalogs=_catalogs())
        result = verifier.verify_entity_file(gar_path)
        codes = {i.code for i in result.issues if i.severity == "error"}
        assert "E140" in codes

    def test_grf_e141_nonexistent_global_entity(self, engagement_root: Path, enterprise_root: Path) -> None:
        gar_id = "GAR@1000000001.AbcDef.ghost-ref"
        gar_path = engagement_root / "model" / "common" / "global-artifact-reference" / f"{gar_id}.md"
        _write(
            gar_path,
            _grf_md(gar_id, "Ghost Ref", "REQ@9999999999.NoExist.nonexistent"),
        )
        # Enterprise repo has real entities but not the referenced one
        _write(
            enterprise_root / "model" / "motivation" / "requirements" / "REQ@2000000000.GloAAA.other.md",
            _entity_md("REQ@2000000000.GloAAA.other", "requirement", "Other"),
        )
        registry = ArtifactRegistry(shared_artifact_index([engagement_root, enterprise_root]))
        verifier = ArtifactVerifier(registry, catalogs=_catalogs())
        result = verifier.verify_entity_file(gar_path)
        codes = {i.code for i in result.issues if i.severity == "error"}
        assert "E141" in codes

    def test_grf_w141_no_enterprise_repo(self, engagement_root: Path) -> None:
        gar_id = "GAR@1000000001.AbcDef.no-ent"
        gar_path = engagement_root / "model" / "common" / "global-artifact-reference" / f"{gar_id}.md"
        _write(gar_path, _grf_md(gar_id, "Some Ref", "REQ@2000000000.GloAAA.unknown"))
        verifier = ArtifactVerifier(None, catalogs=_catalogs())
        result = verifier.verify_entity_file(gar_path)
        codes = {i.code for i in result.issues if i.severity == "warning"}
        errors = {i.code for i in result.issues if i.severity == "error"}
        assert "W141" in codes
        assert "E141" not in errors


# ---------------------------------------------------------------------------
# Transparent GRF routing in model_add_connection
# ---------------------------------------------------------------------------


class TestAddConnectionGrfRouting:
    def _setup_repos(self, engagement_root: Path, enterprise_root: Path) -> tuple[str, str]:
        """Returns (engagement_entity_id, global_entity_id)."""
        eng_id = "CAP@1000000001.EngBBB.my-cap"
        glo_id = "REQ@2000000000.GloAAA.global-req"
        _write(
            engagement_root / "model" / "strategy" / "capabilities" / f"{eng_id}.md",
            _entity_md(eng_id, "capability", "My Cap"),
        )
        _write(
            enterprise_root / "model" / "motivation" / "requirements" / f"{glo_id}.md",
            _entity_md(glo_id, "requirement", "Global Req"),
        )
        return eng_id, glo_id

    def test_connection_to_global_entity_auto_creates_grf(
        self,
        engagement_root: Path,
        enterprise_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _use_workspace_roots(monkeypatch, engagement_root, enterprise_root)
        eng_id, glo_id = self._setup_repos(engagement_root, enterprise_root)

        result = mcp_tools.artifact_add_connection(
            source_entity=eng_id,
            connection_type="archimate-association",
            target_entity=glo_id,
            dry_run=False,
        )

        assert result.get("wrote") is True
        assert result.get("gar_artifact_id", "").startswith("GAR@")
        assert result.get("original_target") == glo_id

        # GAR file should exist in engagement repo
        gar_id = result["gar_artifact_id"]
        gar_dir = engagement_root / "model" / "common" / "global-artifact-reference"
        gar_files = list(gar_dir.rglob("*.md"))
        assert any(gar_id in str(f) for f in gar_files)

        # Outgoing file should reference GAR, not the global entity directly
        outgoing = engagement_root / "model" / "strategy" / "capabilities" / f"{eng_id}.outgoing.md"
        assert outgoing.exists()
        content = outgoing.read_text()
        assert gar_id in content
        assert glo_id not in content

    def test_connection_to_global_entity_reuses_existing_grf(
        self,
        engagement_root: Path,
        enterprise_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _use_workspace_roots(monkeypatch, engagement_root, enterprise_root)
        eng_id, glo_id = self._setup_repos(engagement_root, enterprise_root)

        # First connection creates GRF
        r1 = mcp_tools.artifact_add_connection(
            source_entity=eng_id,
            connection_type="archimate-association",
            target_entity=glo_id,
            dry_run=False,
        )
        gar_id_1 = r1["gar_artifact_id"]

        # Second connection (different source entity) should reuse the same GAR
        eng_id2 = "CAP@1000000002.EngCCC.my-cap2"
        _write(
            engagement_root / "model" / "strategy" / "capabilities" / f"{eng_id2}.md",
            _entity_md(eng_id2, "capability", "My Cap 2"),
        )
        r2 = mcp_tools.artifact_add_connection(
            source_entity=eng_id2,
            connection_type="archimate-association",
            target_entity=glo_id,
            dry_run=False,
        )
        assert r2["gar_artifact_id"] == gar_id_1  # same GAR reused

    def test_connection_between_engagement_entities_unchanged(
        self, engagement_root: Path, enterprise_root: Path
    ) -> None:
        eng_id1 = "CAP@1000000001.EngBBB.cap1"
        eng_id2 = "CAP@1000000002.EngCCC.cap2"
        _write(
            engagement_root / "model" / "strategy" / "capabilities" / f"{eng_id1}.md",
            _entity_md(eng_id1, "capability", "Cap 1"),
        )
        _write(
            engagement_root / "model" / "strategy" / "capabilities" / f"{eng_id2}.md",
            _entity_md(eng_id2, "capability", "Cap 2"),
        )
        result = mcp_tools.artifact_add_connection(
            source_entity=eng_id1,
            connection_type="archimate-aggregation",
            target_entity=eng_id2,
            dry_run=False,
            repo_root=str(engagement_root),
        )
        assert result.get("wrote") is True
        assert "grf_artifact_id" not in result

    def test_connection_from_global_entity_auto_creates_grf_for_source(
        self,
        engagement_root: Path,
        enterprise_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When source is an enterprise entity, a GRF is created and used as source."""
        _use_workspace_roots(monkeypatch, engagement_root, enterprise_root)
        eng_id, glo_id = self._setup_repos(engagement_root, enterprise_root)

        result = mcp_tools.artifact_add_connection(
            source_entity=glo_id,  # enterprise → engagement direction
            connection_type="archimate-association",
            target_entity=eng_id,
            dry_run=False,
        )

        assert result.get("wrote") is True
        assert result.get("gar_source_id", "").startswith("GAR@")
        assert result.get("original_source") == glo_id
        assert "gar_artifact_id" not in result  # target was engagement, no target GAR

        gar_id = result["gar_source_id"]
        gar_dir = engagement_root / "model" / "common" / "global-artifact-reference"
        assert any(gar_id in str(f) for f in gar_dir.rglob("*.md"))

        # Connection stored in GAR's outgoing file, pointing to engagement entity
        gar_outgoing = next(f for f in gar_dir.rglob("*.outgoing.md") if gar_id in str(f))
        content = gar_outgoing.read_text()
        assert eng_id in content
        assert glo_id not in content

    def test_symmetric_connection_with_global_entity_auto_creates_grf(
        self,
        engagement_root: Path,
        enterprise_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """For a symmetric connection where target is enterprise, GRF is created for target."""
        _use_workspace_roots(monkeypatch, engagement_root, enterprise_root)
        eng_id, glo_id = self._setup_repos(engagement_root, enterprise_root)

        result = mcp_tools.artifact_add_connection(
            source_entity=eng_id,
            connection_type="archimate-association",  # symmetric
            target_entity=glo_id,
            dry_run=False,
        )

        assert result.get("wrote") is True
        assert result.get("gar_artifact_id", "").startswith("GAR@")
        assert result.get("original_target") == glo_id

        gar_id = result["gar_artifact_id"]
        outgoing = engagement_root / "model" / "strategy" / "capabilities" / f"{eng_id}.outgoing.md"
        content = outgoing.read_text()
        assert gar_id in content
        assert glo_id not in content

    def test_connection_from_global_reuses_existing_grf(
        self,
        engagement_root: Path,
        enterprise_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A second connection from the same global entity reuses its existing GRF."""
        _use_workspace_roots(monkeypatch, engagement_root, enterprise_root)
        eng_id, glo_id = self._setup_repos(engagement_root, enterprise_root)
        eng_id2 = "CAP@1000000002.EngCCC.cap2"
        _write(
            engagement_root / "model" / "strategy" / "capabilities" / f"{eng_id2}.md",
            _entity_md(eng_id2, "capability", "Cap 2"),
        )

        r1 = mcp_tools.artifact_add_connection(
            source_entity=glo_id,
            connection_type="archimate-association",
            target_entity=eng_id,
            dry_run=False,
        )
        gar_id_1 = r1["gar_source_id"]

        r2 = mcp_tools.artifact_add_connection(
            source_entity=glo_id,
            connection_type="archimate-association",
            target_entity=eng_id2,
            dry_run=False,
        )
        assert r2["gar_source_id"] == gar_id_1


# ---------------------------------------------------------------------------
# Promotion: plan excludes GRFs
# ---------------------------------------------------------------------------


class TestPromotionPlan:
    def test_plan_excludes_grf_entities(self, engagement_root: Path, enterprise_root: Path) -> None:
        from src.infrastructure.write.artifact_write.promote_to_enterprise import plan_promotion

        eng_id = "CAP@1000000001.EngBBB.my-cap"
        gar_id = "GAR@1000000002.GarCCC.gar-ref"
        glo_id = "REQ@2000000000.GloAAA.global-req"

        _write(
            engagement_root / "model" / "strategy" / "capabilities" / f"{eng_id}.md",
            _entity_md(eng_id, "capability", "My Cap"),
        )
        _write(
            engagement_root / "model" / "common" / "global-artifact-reference" / f"{gar_id}.md",
            _grf_md(gar_id, "Global Req Ref", glo_id),
        )
        _write(
            enterprise_root / "model" / "motivation" / "requirements" / f"{glo_id}.md",
            _entity_md(glo_id, "requirement", "Global Req"),
        )
        # Connection from engagement entity to GAR
        _write(
            engagement_root / "model" / "strategy" / "capabilities" / f"{eng_id}.outgoing.md",
            _outgoing_md(eng_id, [("archimate-realization", gar_id)]),
        )

        registry = ArtifactRegistry(shared_artifact_index([engagement_root, enterprise_root]))
        repo = ArtifactRepository(shared_artifact_index([engagement_root, enterprise_root]))
        plan = plan_promotion(eng_id, registry, repo)

        assert eng_id in plan.entities_to_add
        assert gar_id not in plan.entities_to_add
        assert gar_id not in plan.already_in_enterprise

    def test_plan_exclude_params(self, engagement_root: Path, enterprise_root: Path) -> None:
        from src.infrastructure.write.artifact_write.promote_to_enterprise import plan_promotion

        eng_id1 = "CAP@1000000001.EngBBB.cap1"
        eng_id2 = "CAP@1000000002.EngCCC.cap2"
        for eid, name in [(eng_id1, "Cap 1"), (eng_id2, "Cap 2")]:
            _write(
                engagement_root / "model" / "strategy" / "capabilities" / f"{eid}.md",
                _entity_md(eid, "capability", name),
            )
        _write(
            engagement_root / "model" / "strategy" / "capabilities" / f"{eng_id1}.outgoing.md",
            _outgoing_md(eng_id1, [("archimate-aggregation", eng_id2)]),
        )

        registry = ArtifactRegistry(shared_artifact_index([engagement_root, enterprise_root]))
        repo = ArtifactRepository(shared_artifact_index([engagement_root, enterprise_root]))
        plan = plan_promotion(
            eng_id1,
            registry,
            repo,
            entity_ids=[eng_id1, eng_id2],
            exclude_entity_ids={eng_id2},
        )
        assert eng_id1 in plan.entities_to_add
        assert eng_id2 not in plan.entities_to_add


# ---------------------------------------------------------------------------
# Promotion execute: outgoing rewrite
# ---------------------------------------------------------------------------


class TestPromotionExecuteOutgoingRewrite:
    def test_grf_targets_rewritten_to_enterprise_ids(self, engagement_root: Path, enterprise_root: Path) -> None:
        from src.infrastructure.write.artifact_write._promote_file_ops import make_target_resolver
        from src.infrastructure.write.artifact_write._promote_file_ops import rewrite_outgoing as _rewrite_outgoing
        from src.infrastructure.write.artifact_write.promote_to_enterprise import PromotionPlan, PromotionResult

        gar_id = "GAR@1000000002.GarCCC.gar-ref"
        glo_id = "REQ@2000000000.GloAAA.global-req"
        eng_id = "CAP@1000000001.EngBBB.my-cap"

        content = _outgoing_md(
            eng_id,
            [
                ("archimate-realization", gar_id),
                ("archimate-serving", glo_id),  # already enterprise
            ],
        )

        plan = PromotionPlan(
            root_entity=eng_id,
            entities_to_add=[eng_id],
            conflicts=[],
            connection_ids=[],
            already_in_enterprise=[],
            warnings=[],
        )
        result = PromotionResult(plan=plan, executed=False)

        resolver = make_target_resolver(
            gar_map={gar_id: glo_id},
            promoted_ids={eng_id},
            enterprise_ids={glo_id},
        )
        rewritten = _rewrite_outgoing(
            content,
            resolve_target=resolver,
            result=result,
            conn_ids={f"{eng_id}---{gar_id}@@archimate-realization"},
        )

        assert gar_id not in rewritten
        assert glo_id in rewritten
        assert "archimate-realization" in rewritten
        assert "archimate-serving" not in rewritten

    def test_stranded_targets_dropped_with_warning(self, engagement_root: Path, enterprise_root: Path) -> None:
        from src.infrastructure.write.artifact_write._promote_file_ops import make_target_resolver
        from src.infrastructure.write.artifact_write._promote_file_ops import rewrite_outgoing as _rewrite_outgoing
        from src.infrastructure.write.artifact_write.promote_to_enterprise import PromotionPlan, PromotionResult

        eng_id = "CAP@1000000001.EngBBB.my-cap"
        other_eng = "CAP@1000000003.EngDDD.other"

        content = _outgoing_md(
            eng_id,
            [
                ("archimate-serving", other_eng),
            ],
        )
        plan = PromotionPlan(
            root_entity=eng_id,
            entities_to_add=[eng_id],
            conflicts=[],
            connection_ids=[],
            already_in_enterprise=[],
            warnings=[],
        )
        result = PromotionResult(plan=plan, executed=False)
        resolver = make_target_resolver({}, promoted_ids={eng_id}, enterprise_ids=set())
        rewritten = _rewrite_outgoing(
            content,
            resolve_target=resolver,
            result=result,
            conn_ids=None,  # None = include all; lets stranded targets reach the warning path
        )

        assert other_eng not in rewritten
        assert any(other_eng in w for w in result.plan.warnings)


# ---------------------------------------------------------------------------
# Promotion execute: full round-trip (enterprise copy + engagement GRF replacement)
# ---------------------------------------------------------------------------


class TestPromotionExecuteFullRoundTrip:
    def _setup(self, engagement_root: Path, enterprise_root: Path) -> tuple[str, str, str]:
        """Create eng entity with GAR connection. Returns (eng_id, gar_id, glo_id)."""
        eng_id = "CAP@1000000001.EngBBB.my-cap"
        gar_id = "GAR@1000000002.GarCCC.gar-ref"
        glo_id = "REQ@2000000000.GloAAA.global-req"

        _write(
            engagement_root / "model" / "strategy" / "capabilities" / f"{eng_id}.md",
            _entity_md(eng_id, "capability", "My Cap"),
        )
        _write(
            engagement_root / "model" / "common" / "global-artifact-reference" / f"{gar_id}.md",
            _grf_md(gar_id, "Global Req Ref", glo_id),
        )
        _write(
            engagement_root / "model" / "strategy" / "capabilities" / f"{eng_id}.outgoing.md",
            _outgoing_md(eng_id, [("archimate-realization", gar_id)]),
        )
        _write(
            enterprise_root / "model" / "motivation" / "requirements" / f"{glo_id}.md",
            _entity_md(glo_id, "requirement", "Global Req"),
        )
        return eng_id, gar_id, glo_id

    def test_entity_copied_to_enterprise(self, engagement_root: Path, enterprise_root: Path) -> None:
        from src.infrastructure.write.artifact_write.promote_execute import execute_promotion
        from src.infrastructure.write.artifact_write.promote_to_enterprise import plan_promotion

        eng_id, _, _ = self._setup(engagement_root, enterprise_root)
        registry = ArtifactRegistry(shared_artifact_index([engagement_root, enterprise_root]))
        repo = ArtifactRepository(shared_artifact_index([engagement_root, enterprise_root]))

        plan = plan_promotion(eng_id, registry, repo)
        result = execute_promotion(plan, engagement_root, enterprise_root, registry)

        assert result.executed, result.verification_errors
        ent_file = enterprise_root / "model" / "strategy" / "capabilities" / f"{eng_id}.md"
        assert ent_file.exists()

    def test_grf_target_rewritten_in_enterprise_outgoing(self, engagement_root: Path, enterprise_root: Path) -> None:
        from src.infrastructure.write.artifact_write.promote_execute import execute_promotion
        from src.infrastructure.write.artifact_write.promote_to_enterprise import plan_promotion

        eng_id, gar_id, glo_id = self._setup(engagement_root, enterprise_root)
        registry = ArtifactRegistry(shared_artifact_index([engagement_root, enterprise_root]))
        repo = ArtifactRepository(shared_artifact_index([engagement_root, enterprise_root]))

        plan = plan_promotion(eng_id, registry, repo)
        result = execute_promotion(plan, engagement_root, enterprise_root, registry)

        assert result.executed, result.verification_errors
        ent_outgoing = enterprise_root / "model" / "strategy" / "capabilities" / f"{eng_id}.outgoing.md"
        assert ent_outgoing.exists()
        content = ent_outgoing.read_text()
        assert gar_id not in content, "GAR should be rewritten to enterprise entity"
        assert glo_id in content, "Real enterprise entity should appear in outgoing"

    def test_promoted_engagement_entity_replaced_by_grf(self, engagement_root: Path, enterprise_root: Path) -> None:
        from src.infrastructure.write.artifact_write.promote_execute import execute_promotion
        from src.infrastructure.write.artifact_write.promote_to_enterprise import plan_promotion

        eng_id, _, _ = self._setup(engagement_root, enterprise_root)
        orig_eng_file = engagement_root / "model" / "strategy" / "capabilities" / f"{eng_id}.md"
        registry = ArtifactRegistry(shared_artifact_index([engagement_root, enterprise_root]))
        repo = ArtifactRepository(shared_artifact_index([engagement_root, enterprise_root]))

        plan = plan_promotion(eng_id, registry, repo)
        result = execute_promotion(plan, engagement_root, enterprise_root, registry)

        assert result.executed, result.verification_errors
        # Original engagement entity file removed
        assert not orig_eng_file.exists(), "Original engagement entity should be replaced by GAR"
        # A new GAR for the promoted entity should exist
        gar_dir = engagement_root / "model" / "common" / "global-artifact-reference"
        new_gars = [f for f in gar_dir.rglob("GAR@*.md") if eng_id in f.read_text()]
        assert new_gars, "A GAR pointing to the promoted entity should be created"

    def test_outgoing_references_updated_after_replacement(self, engagement_root: Path, enterprise_root: Path) -> None:
        from src.infrastructure.write.artifact_write.promote_execute import execute_promotion
        from src.infrastructure.write.artifact_write.promote_to_enterprise import plan_promotion

        eng_id, _, _ = self._setup(engagement_root, enterprise_root)

        # Add a second engagement entity that connects TO eng_id
        other_eng = "CAP@1000000099.EngEEE.other-cap"
        _write(
            engagement_root / "model" / "strategy" / "capabilities" / f"{other_eng}.md",
            _entity_md(other_eng, "capability", "Other Cap"),
        )
        # Keep this entity outside the explicit promotion selection.
        _write(
            engagement_root / "model" / "strategy" / "capabilities" / f"{other_eng}.outgoing.md",
            _outgoing_md(other_eng, [("archimate-influence", eng_id)]),
        )

        registry = ArtifactRegistry(shared_artifact_index([engagement_root, enterprise_root]))
        repo = ArtifactRepository(shared_artifact_index([engagement_root, enterprise_root]))

        plan = plan_promotion(eng_id, registry, repo)
        result = execute_promotion(plan, engagement_root, enterprise_root, registry)

        assert result.executed, result.verification_errors
        # The other engagement entity's outgoing should now reference the new GAR
        other_outgoing = engagement_root / "model" / "strategy" / "capabilities" / f"{other_eng}.outgoing.md"
        content = other_outgoing.read_text()
        assert eng_id not in content, "Old entity ID should be replaced in cross-references"
        assert "GAR@" in content, "Reference should point to new GAR"

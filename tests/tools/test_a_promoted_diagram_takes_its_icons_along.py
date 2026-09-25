"""A promoted diagram takes along the library icons it shows that only the engagement holds (D6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.artifact_index import combined_artifact_index
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp import context as ctx
from src.infrastructure.rendering.generate_static_includes import generate_static_includes
from src.infrastructure.write.artifact_write.promote_execute import execute_promotion
from src.infrastructure.write.artifact_write.promote_to_enterprise import plan_promotion
from tests.support.icon_files import icon_file, write_icon

AKS = "ICO@1790000000.aks001.azure-kubernetes-service"


@pytest.fixture
def roots(tmp_path: Path) -> tuple[Path, Path]:
    eng = tmp_path / "engagements" / "ENG-ICO" / "architecture-repository"
    ent = tmp_path / "enterprise-repository"
    for root in (eng, ent):
        for directory in ("model", "docs", "diagram-catalog/diagrams"):
            (root / directory).mkdir(parents=True, exist_ok=True)
        generate_static_includes(root)
    return eng, ent


def _diagram_showing(eng: Path, icon_id: str) -> tuple[str, str]:
    node = str(mcp.artifact_create_entity(
        artifact_type="technology-node", name="Cluster", dry_run=False, repo_root=str(eng)
    )["artifact_id"])
    diagram = mcp.artifact_create_diagram(
        diagram_type="archimate-technology", name="Clusters", entity_ids=[node],
        diagram_entities={"display_icons": {node: icon_id}}, dry_run=False, repo_root=str(eng),
    )
    assert diagram["wrote"] is True, diagram["verification"]
    return node, str(diagram["artifact_id"])


def _plan(eng: Path, ent: Path, **kwargs):
    index = combined_artifact_index(eng, ent)
    registry = ArtifactRegistry(index)
    repo = ArtifactRepository(index)
    return plan_promotion(None, registry, repo, engagement_root=eng, enterprise_root=ent, **kwargs), registry


def test_an_icon_only_the_engagement_holds_is_planned_and_lands_in_the_enterprise(roots) -> None:
    eng, ent = roots
    write_icon(eng, icon_file(AKS, applies_to=("technology-node",)))
    node, diagram = _diagram_showing(eng, AKS)

    plan, registry = _plan(eng, ent, entity_ids=[node], diagram_ids=[diagram])
    assert plan.icons_to_add == [AKS]

    result = execute_promotion(plan, eng, ent, registry)
    assert result.executed is True, result.verification_errors
    assert (ent / "diagram-catalog" / "icons" / f"{AKS}.md").exists()
    assert (eng / "diagram-catalog" / "icons" / f"{AKS}.md").exists()


def test_an_icon_the_enterprise_already_holds_is_usable_and_stays_behind(roots, monkeypatch) -> None:
    """An engagement write sees its workspace's enterprise library: no proxy stands in for an icon."""
    eng, ent = roots
    monkeypatch.setattr(ctx, "_workspace_repo_roots", lambda: (eng, ent))
    write_icon(ent, icon_file(AKS, applies_to=("technology-node",)))
    node, diagram = _diagram_showing(eng, AKS)

    plan, _ = _plan(eng, ent, entity_ids=[node], diagram_ids=[diagram])

    assert plan.icons_to_add == []

"""A promoted diagram takes along the library icons it shows that only the engagement holds (D6).

One whose picture the enterprise already holds under another id stays behind, and the promoted diagram
names the enterprise's icon instead.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.domain.artifact_id import stable_id
from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.artifact_index import combined_artifact_index
from src.infrastructure.artifact_index.bootstrap import notify_paths_changed
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp import context as ctx
from src.infrastructure.rendering.generate_static_includes import generate_static_includes
from src.infrastructure.write.artifact_write.promote_execute import execute_promotion
from src.infrastructure.write.artifact_write.promote_to_enterprise import ConflictResolution, plan_promotion
from tests.support.icon_files import icon_file, write_icon

AKS = "ICO@1790000000.aks001.azure-kubernetes-service"
#: The engagement's own upload of the same logo, under an id of its own.
OWN_AKS = "ICO@1790000003.own001.aks-logo"


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


def _promoted_display_icons(ent: Path, diagram_id: str) -> dict:
    [path] = (ent / "diagram-catalog" / "diagrams").rglob(f"{stable_id(diagram_id)}*.puml")
    return parse_frontmatter(path.read_text(encoding="utf-8"))["diagram-entities"]["display_icons"]  # type: ignore[index]


@pytest.mark.verifies("REQ@1790305394.1bkWD0Y")
def test_a_picture_the_enterprise_holds_under_another_id_is_named_there_and_not_copied(roots, monkeypatch) -> None:
    eng, ent = roots
    monkeypatch.setattr(ctx, "_workspace_repo_roots", lambda: (eng, ent))
    write_icon(ent, icon_file(AKS, applies_to=("technology-node",)))
    write_icon(eng, icon_file(OWN_AKS, applies_to=("technology-node",)))
    node, diagram = _diagram_showing(eng, OWN_AKS)

    plan, registry = _plan(eng, ent, entity_ids=[node], diagram_ids=[diagram])
    assert (plan.icons_to_add, plan.icons_held_by_picture) == ([], {OWN_AKS: AKS})

    result = execute_promotion(plan, eng, ent, registry)
    assert result.executed is True, result.verification_errors
    assert list(_promoted_display_icons(ent, diagram).values()) == [stable_id(AKS)]
    assert not (ent / "diagram-catalog" / "icons" / f"{OWN_AKS}.md").exists()


def test_an_accepted_engagement_version_of_a_diagram_takes_its_icons_along(roots) -> None:
    """A conflict resolved to the engagement's diagram copies that diagram, so its icons must travel too."""
    eng, ent = roots
    write_icon(eng, icon_file(AKS, applies_to=("technology-node",)))
    other = str(mcp.artifact_create_entity(
        artifact_type="technology-node", name="Other", dry_run=False, repo_root=str(eng)
    )["artifact_id"])
    # The enterprise's own "Clusters", by type and name; the accepted engagement version overwrites it.
    earlier = mcp.artifact_create_diagram(
        diagram_type="archimate-technology", name="Clusters", entity_ids=[other], dry_run=False, repo_root=str(eng),
    )
    assert earlier["wrote"] is True, earlier
    earlier_path = Path(str(earlier["path"]))
    enterprise_copy = ent / earlier_path.relative_to(eng)
    enterprise_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(earlier_path, enterprise_copy)
    notify_paths_changed([earlier_path])
    node, diagram = _diagram_showing(eng, AKS)

    plan, registry = _plan(eng, ent, entity_ids=[node], diagram_ids=[diagram])
    assert [c.engagement_id for c in plan.diagram_conflicts] == [diagram]
    assert plan.icons_to_add == [AKS]

    resolutions = [ConflictResolution(engagement_id=diagram, strategy="accept_engagement")]
    result = execute_promotion(plan, eng, ent, registry, conflict_resolutions=resolutions)
    assert result.executed is True, result.verification_errors
    assert (ent / "diagram-catalog" / "icons" / f"{AKS}.md").exists()

"""Plan-time purpose-line closure: a promoted diagram's or promoted-alongside viewpoint's stakeholder or
concern reference must name an element the enterprise holds after the promotion. One that would dangle is
refused before anything is written and named as a `purpose_line_reference` missing dependency; the same
element carried along in the same plan, or already enterprise-side, satisfies it; prose is never looked at.

Against fixture repositories this file builds, so exact contents are the test's own.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.domain.purpose_lines import Prose, Reference
from src.domain.viewpoints.viewpoints import ViewpointCatalog, ViewpointDefinition
from src.infrastructure.artifact_index import combined_artifact_index
from src.infrastructure.viewpoint_declarations import write_viewpoint_catalog_file
from src.infrastructure.write.artifact_write.promote_execute import execute_promotion
from src.infrastructure.write.artifact_write.promote_to_enterprise import plan_promotion

_STK = "STK@1000000801.PplStk.purpose-stakeholder"
_GOL = "GOL@1000000802.PplGol.purpose-goal"
_ARC = "ARC@1000000803.PplArc.purpose-diagram"
_SLUG = "purpose-closure-viewpoint"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _entity_md(artifact_id: str, artifact_type: str, name: str) -> str:
    prefix, rand = artifact_id.split("@")[0], artifact_id.split(".")[1]
    return (
        f"---\nartifact-id: {artifact_id}\nartifact-type: {artifact_type}\nname: \"{name}\"\nversion: 0.1.0\n"
        f"status: draft\nlast-updated: '2026-01-01'\n---\n\n<!-- §content -->\n\n## {name}\n\n"
        f"<!-- §display -->\n\n### archimate\n\n```yaml\nlabel: \"{name}\"\nalias: {prefix}_{rand}\n```\n"
    )


def _diagram_puml(frontmatter_tail: str) -> str:
    return (
        f"---\nartifact-id: {_ARC}\nartifact-type: diagram\ndiagram-type: archimate-motivation\n"
        "name: Purpose Diagram\nstatus: draft\nversion: 0.1.0\nlast-updated: '2026-01-01'\n"
        f"entity-ids-used: []\nconnection-ids-used: []\n{frontmatter_tail}---\n"
        "@startuml\ntitle Purpose Diagram\n@enduml\n"
    )


@pytest.fixture()
def roots(tmp_path: Path) -> tuple[Path, Path]:
    eng = tmp_path / "engagements" / "ENG-PPL" / "architecture-repository"
    ent = tmp_path / "enterprise-repository"
    for root in (eng, ent):
        (root / "model").mkdir(parents=True, exist_ok=True)
    _write(eng / "model/motivation/stakeholder" / f"{_STK}.md", _entity_md(_STK, "stakeholder", "Operations"))
    _write(eng / "model/motivation/goal" / f"{_GOL}.md", _entity_md(_GOL, "goal", "Fast"))
    return eng, ent


def _diagram(eng: Path, frontmatter_tail: str) -> None:
    _write(eng / "diagram-catalog/diagrams/purpose" / f"{_ARC}.puml", _diagram_puml(frontmatter_tail))


def _plan(eng: Path, ent: Path, **kwargs):
    index = combined_artifact_index(eng, ent)
    registry = ArtifactRegistry(index)
    return plan_promotion(
        None, registry, ArtifactRepository(index), engagement_root=eng, enterprise_root=ent, **kwargs
    ), registry


def _purpose_deps(plan) -> list[tuple[str, str]]:
    return [(d.artifact_id, d.required_by) for d in plan.missing_dependencies if d.kind == "purpose_line_reference"]


class TestDiagramPurposeLines:
    def test_a_reference_left_engagement_side_is_refused_before_anything_is_written(self, roots) -> None:
        eng, ent = roots
        _diagram(eng, f"stakeholders:\n- ref: {_STK}\n")

        plan, registry = _plan(eng, ent, diagram_ids=[_ARC])

        assert _purpose_deps(plan) == [(_STK, _ARC)]
        assert any(_STK in error and _ARC in error for error in plan.schema_errors)
        result = execute_promotion(plan, eng, ent, registry)
        assert result.executed is False and result.copied_files == []

    def test_the_element_carried_along_in_the_same_plan_satisfies_it(self, roots) -> None:
        eng, ent = roots
        _diagram(eng, f"stakeholders:\n- ref: {_STK}\nconcerns:\n- ref: {_GOL}\n")

        plan, _ = _plan(eng, ent, diagram_ids=[_ARC], entity_ids=[_STK, _GOL])

        assert _purpose_deps(plan) == []

    def test_an_element_the_enterprise_already_holds_satisfies_it(self, roots) -> None:
        eng, ent = roots
        _write(ent / "model/motivation/stakeholder" / f"{_STK}.md", _entity_md(_STK, "stakeholder", "Operations"))
        _diagram(eng, f"stakeholders:\n- ref: {_STK}\n")

        plan, _ = _plan(eng, ent, diagram_ids=[_ARC])

        assert _purpose_deps(plan) == []

    def test_prose_entries_name_nothing_and_are_not_looked_at(self, roots) -> None:
        eng, ent = roots
        _diagram(eng, "stakeholders:\n- Operations team\nconcerns:\n- How fast is an order shipped?\n")

        plan, _ = _plan(eng, ent, diagram_ids=[_ARC])

        assert _purpose_deps(plan) == []


class TestViewpointPromotedAlongside:
    def _viewpoint(self, eng: Path) -> None:
        definition = ViewpointDefinition(
            slug=_SLUG, version=1, name="Purpose closure",
            stakeholders=(Prose("Operations team"), Reference(_STK)), concerns=(Reference(_GOL),),
        )
        write_viewpoint_catalog_file(eng, ViewpointCatalog((definition,)))
        _diagram(eng, f"viewpoint:\n  slug: {_SLUG}\n  version: 1\n")

    def test_its_dangling_reference_is_refused(self, roots) -> None:
        eng, ent = roots
        self._viewpoint(eng)

        plan, _ = _plan(eng, ent, diagram_ids=[_ARC], viewpoint_resolutions={_SLUG: "promote_alongside"})

        required_by = f"viewpoint '{_SLUG}'"
        assert sorted(_purpose_deps(plan)) == sorted([(_STK, required_by), (_GOL, required_by)])
        assert any(_STK in error and required_by in error for error in plan.schema_errors)

    def test_the_elements_carried_along_satisfy_it(self, roots) -> None:
        eng, ent = roots
        self._viewpoint(eng)

        plan, _ = _plan(
            eng, ent, diagram_ids=[_ARC], entity_ids=[_STK, _GOL], viewpoint_resolutions={_SLUG: "promote_alongside"}
        )

        assert _purpose_deps(plan) == []
        assert plan.schema_errors == []

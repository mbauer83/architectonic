"""Structural-closure preflight: junctions and groupings cannot be promoted without the
entities that give them meaning — the plan blocks with the exact missing ids instead of
silently dropping the connections that ARE the junction's logic / the grouping's
membership."""

from __future__ import annotations

from pathlib import Path

from src.application.artifact_query import ArtifactRepository
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.promote_to_enterprise import plan_promotion


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _entity_md(artifact_id: str, artifact_type: str, name: str) -> str:
    prefix = artifact_id.split("@")[0]
    rand = artifact_id.split(".")[1]
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: {artifact_type}
name: "{name}"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
---

<!-- §content -->

## {name}

<!-- §display -->

### archimate

```yaml
label: "{name}"
alias: {prefix}_{rand}
```
"""


def _outgoing_md(source_id: str, declarations: list[tuple[str, str]]) -> str:
    sections = "\n".join(f"### {conn_type} → {target}\n" for conn_type, target in declarations)
    return f"""\
---
source-entity: {source_id}
version: 0.1.0
status: draft
last-updated: '2026-01-01'
---

<!-- §connections -->

{sections}
"""


_R1 = "REQ@1000000501.ClosR1.first-requirement"
_R2 = "REQ@1000000502.ClosR2.second-requirement"
_JN = "JNO@1000000503.ClosJn.decision-junction"
_GRP = "GRP@1000000504.ClosGr.feature-grouping"
_M1 = "APP@1000000505.ClosM1.member-component"


def _plant(root: Path) -> None:
    _write(root / "model/motivation/requirement" / f"{_R1}.md", _entity_md(_R1, "requirement", "First"))
    _write(root / "model/motivation/requirement" / f"{_R2}.md", _entity_md(_R2, "requirement", "Second"))
    _write(root / "model/common/or-junction" / f"{_JN}.md", _entity_md(_JN, "or-junction", "Either"))
    _write(root / "model/common/grouping" / f"{_GRP}.md", _entity_md(_GRP, "grouping", "Feature"))
    _write(
        root / "model/application/application-component" / f"{_M1}.md",
        _entity_md(_M1, "application-component", "Member"),
    )
    # R1 → junction → R2 (the junction's whole meaning), grouping composes M1.
    _write(
        root / "model/motivation/requirement" / f"{_R1}.outgoing.md",
        _outgoing_md(_R1, [("archimate-influence", _JN)]),
    )
    _write(
        root / "model/common/or-junction" / f"{_JN}.outgoing.md",
        _outgoing_md(_JN, [("archimate-influence", _R2)]),
    )
    _write(
        root / "model/common/grouping" / f"{_GRP}.outgoing.md",
        _outgoing_md(_GRP, [("archimate-composition", _M1)]),
    )


def _deps(tmp_path: Path) -> tuple[Path, ArtifactRepository, ArtifactRegistry]:
    root = tmp_path / "engagements" / "ENG-CLOS" / "architecture-repository"
    _plant(root)
    index = shared_artifact_index([root])
    return root, ArtifactRepository(index), ArtifactRegistry(index)


class TestJunctionClosure:
    def test_junction_alone_blocks_with_the_missing_endpoints(self, tmp_path: Path) -> None:
        _, repo, registry = _deps(tmp_path)
        plan = plan_promotion(_JN, registry, repo)
        closure_errors = [e for e in plan.schema_errors if "structural closure" in e]
        assert len(closure_errors) == 1
        assert _R1 in closure_errors[0]
        assert _R2 in closure_errors[0]

    def test_plan_carries_structured_requirements_with_names(self, tmp_path: Path) -> None:
        _, repo, registry = _deps(tmp_path)
        plan = plan_promotion(_JN, registry, repo)
        assert len(plan.structural_closure) == 1
        requirement = plan.structural_closure[0]
        assert requirement.kind == "junction"
        assert requirement.entity_id == _JN
        assert requirement.entity_name == "Either"
        missing = {m.artifact_id: m for m in requirement.missing}
        assert set(missing) == {_R1, _R2}
        assert missing[_R1].name == "First"
        assert missing[_R1].artifact_type == "requirement"

    def test_junction_with_all_endpoints_passes(self, tmp_path: Path) -> None:
        _, repo, registry = _deps(tmp_path)
        plan = plan_promotion(None, registry, repo, entity_ids=[_JN, _R1, _R2])
        assert not [e for e in plan.schema_errors if "structural closure" in e]


class TestGroupingClosure:
    def test_grouping_alone_blocks_with_the_missing_members(self, tmp_path: Path) -> None:
        _, repo, registry = _deps(tmp_path)
        plan = plan_promotion(_GRP, registry, repo)
        closure_errors = [e for e in plan.schema_errors if "structural closure" in e]
        assert len(closure_errors) == 1
        assert _M1 in closure_errors[0]

    def test_grouping_with_members_passes(self, tmp_path: Path) -> None:
        _, repo, registry = _deps(tmp_path)
        plan = plan_promotion(None, registry, repo, entity_ids=[_GRP, _M1])
        assert not [e for e in plan.schema_errors if "structural closure" in e]
        assert plan.structural_closure == []

    def test_plain_entities_are_unaffected(self, tmp_path: Path) -> None:
        _, repo, registry = _deps(tmp_path)
        plan = plan_promotion(_M1, registry, repo)
        assert not [e for e in plan.schema_errors if "structural closure" in e]

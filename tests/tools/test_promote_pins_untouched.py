"""Viewpoint pins are a repo-local sidecar (``.arch-repo/viewpoint-pins.yaml``), never
definition content — a real cross-repo promotion must never copy or reference it."""

from __future__ import annotations

from pathlib import Path

from src.application.artifact_query import ArtifactRepository
from src.application.verification.artifact_verifier import ArtifactRegistry
from src.application.viewpoints.pins import save_pinned_slugs
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.promote_execute import execute_promotion
from src.infrastructure.write.artifact_write.promote_to_enterprise import plan_promotion

_ENTITY_ID = "REQ@1000000095.EntPin1.promote-with-pins"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _entity_md(artifact_id: str, name: str) -> str:
    slug = artifact_id.split(".")[-1].replace("-", "_")
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

Entity for promotion-untouched-pins testing.

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


class TestPromotionNeverTouchesPins:
    def test_real_execution_leaves_the_pins_sidecar_untouched(self, tmp_path: Path) -> None:
        engagement_root = tmp_path / "engagements" / "ENG-PIN" / "architecture-repository"
        enterprise_root = tmp_path / "enterprise-repository"
        enterprise_root.mkdir(parents=True)
        _write(
            engagement_root / "model" / "motivation" / "requirement" / f"{_ENTITY_ID}.md",
            _entity_md(_ENTITY_ID, "Pin Entity"),
        )
        save_pinned_slugs(engagement_root, ("some-viewpoint",))

        repo = ArtifactRepository(shared_artifact_index([engagement_root]))
        registry = ArtifactRegistry(shared_artifact_index([engagement_root, enterprise_root]))
        plan = plan_promotion(_ENTITY_ID, registry, repo)
        result = execute_promotion(plan, engagement_root, enterprise_root, registry)

        assert result.executed is True
        assert not (enterprise_root / ".arch-repo" / "viewpoint-pins.yaml").exists()
        assert (engagement_root / ".arch-repo" / "viewpoint-pins.yaml").exists()
        assert all("viewpoint-pins" not in copied for copied in result.copied_files)

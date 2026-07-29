from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock

from src.application.artifact_query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.gui.routers import entities as entity_router
from src.infrastructure.gui.routers import state as gui_state

_MOCK_REQUEST = MagicMock()  # request object never accessed when meta_ontology is absent


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _entity_md(artifact_id: str, name: str) -> str:
    suffix = artifact_id.split(".")[-1].replace("-", "_")
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: requirement
name: "{name}"
version: 0.1.0
status: active
last-updated: '2026-04-27'
keywords:
  - load
  - performance
---

<!-- §content -->

## {name}

This entity exists to exercise concurrent read performance.

## Properties

| Attribute | Value |
|---|---|
| owner | team-{suffix} |

## Notes

Read-heavy regression coverage.

<!-- §display -->

### archimate

```yaml
domain: Motivation
element-type: Requirement
label: "{name}"
alias: REQ_{suffix}
```
"""


def _outgoing_md(source_entity: str, target_entity: str) -> str:
    return f"""\
---
source-entity: {source_entity}
version: 0.1.0
status: active
last-updated: '2026-04-27'
---

<!-- §connections -->

### archimate-association → {target_entity}

### archimate-composition → {target_entity}
"""


def test_parallel_read_endpoints_hold_up_under_moderate_concurrency(tmp_path: Path) -> None:
    repo_root = tmp_path / "engagements" / "ENG-PERF" / "architecture-repository"
    model_root = repo_root / "model" / "motivation" / "requirements"
    entity_ids: list[str] = []

    for idx in range(160):
        artifact_id = f"REQ@2000000{idx:03d}.T{idx:03d}.entity-{idx}"
        entity_ids.append(artifact_id)
        _write(model_root / f"{artifact_id}.md", _entity_md(artifact_id, f"Entity {idx}"))

    for idx in range(len(entity_ids) - 1):
        _write(
            model_root / f"{entity_ids[idx]}.outgoing.md",
            _outgoing_md(entity_ids[idx], entity_ids[idx + 1]),
        )

    repo = ArtifactRepository(shared_artifact_index([repo_root]))
    gui_state.init_state(repo, repo_root, None)

    # Warm the shared index before starting the timed parallel section.
    warm_context = entity_router.read_entity_context(entity_ids[0])
    warm_list = entity_router.list_entities(_MOCK_REQUEST, domain="motivation", limit=50, offset=0)
    assert warm_context["entity"]["artifact_id"] == entity_ids[0]
    assert warm_list["total"] == len(entity_ids)

    def _run_task(task_index: int) -> str:
        entity_id = entity_ids[task_index % len(entity_ids)]
        if task_index % 3 == 0:
            payload = entity_router.read_entity_context(entity_id)
            return str(payload["entity"]["artifact_id"])
        page = entity_router.list_entities(
            _MOCK_REQUEST,
            domain="motivation",
            limit=50,
            offset=(task_index % 3) * 50,
        )
        return str(page["items"][0]["artifact_id"]) if page["items"] else ""

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(_run_task, range(180)))
    elapsed_s = time.perf_counter() - started

    assert len(results) == 180
    assert all(result for result in results)
    # Keep the threshold loose enough for CI variance while still catching severe regressions.
    assert elapsed_s < 12.0

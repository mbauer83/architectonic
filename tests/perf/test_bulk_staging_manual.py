from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pytest

from src.infrastructure.mcp.artifact_mcp.bulk_tools import artifact_bulk_delete, artifact_bulk_write
from src.infrastructure.write.operation_registry import operation_registry

pytestmark = [
    pytest.mark.perf_manual,
    pytest.mark.skipif(os.environ.get("ARCH_PERF_MANUAL") != "1", reason="set ARCH_PERF_MANUAL=1 to run"),
]


def test_manual_bulk_pipeline_profile(tmp_path: Path) -> None:
    entity_count = int(os.environ.get("ARCH_PERF_ENTITY_COUNT", "1000"))
    batch_size = int(os.environ.get("ARCH_PERF_BATCH_SIZE", "10"))
    repo = _synthetic_repo(tmp_path, entity_count)

    phases: list[dict[str, Any]] = []
    original_set_phase = operation_registry.set_phase

    def recording_set_phase(operation_id: str, phase: str) -> None:
        phases.append({"operation_id": operation_id, "phase": phase, "t": time.perf_counter()})
        original_set_phase(operation_id, phase)

    operation_registry.set_phase = recording_set_phase  # type: ignore[method-assign]
    try:
        started = time.perf_counter()
        write_result = artifact_bulk_write(
            repo_root=str(repo),
            dry_run=False,
            items=[
                {
                    "op": "edit_entity",
                    "artifact_id": f"REQ@0000000000.{index:06d}.entity-{index}",
                    "summary": f"Updated {index}",
                }
                for index in range(batch_size)
            ],
        )
        write_elapsed = time.perf_counter() - started

        started = time.perf_counter()
        delete_result = artifact_bulk_delete(
            repo_root=str(repo),
            dry_run=False,
            items=[
                {
                    "op": "delete_entity",
                    "artifact_id": f"REQ@0000000000.{index + batch_size:06d}.entity-{index + batch_size}",
                }
                for index in range(batch_size)
            ],
        )
        delete_elapsed = time.perf_counter() - started
    finally:
        operation_registry.set_phase = original_set_phase  # type: ignore[method-assign]

    assert all(item.get("wrote") for item in write_result)
    assert all(item.get("wrote") for item in delete_result["results"])
    print(
        {
            "entity_count": entity_count,
            "batch_size": batch_size,
            "bulk_write_s": write_elapsed,
            "bulk_delete_s": delete_elapsed,
            "phase_events": phases,
        }
    )


def _synthetic_repo(tmp_path: Path, entity_count: int) -> Path:
    repo = tmp_path / "engagement" / "architecture-repository"
    model = repo / "model" / "strategy" / "requirement"
    model.mkdir(parents=True)
    for index in range(entity_count):
        artifact_id = f"REQ@0000000000.{index:06d}.entity-{index}"
        (model / f"{artifact_id}.md").write_text(
            f"""\
---
artifact-id: {artifact_id}
artifact-type: requirement
name: Entity {index}
summary: Entity {index}
status: draft
version: 0.1.0
last-updated: '2026-07-05'
---
""",
            encoding="utf-8",
        )
    return repo

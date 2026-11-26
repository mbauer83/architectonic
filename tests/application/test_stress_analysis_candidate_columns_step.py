"""`stress-analysis-candidate-columns`: a stored stress-analysis type whose adaptation and verdict columns name a
candidate in plain text is given the shipped `id` declaration of each — a column typed otherwise, and every other
key, left as they were, and a second run a no-op.

Regression: an adaptation row naming its candidate by a short id, or by an id nothing stores, verified clean,
because the repository's own type kept the untyped columns the shipped type has since typed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.application.repository_upgrade.registry import DEFAULT_REGISTRY
from src.application.repository_upgrade.steps.stress_analysis_candidate_columns import (
    StressAnalysisCandidateColumnsStep,
)
from src.domain.repository.repo_default_stress_analysis import STRESS_ANALYSIS_SCHEMA
from src.infrastructure.repository_upgrade.fs_adapter import FilesystemRepoUpgradeView, FilesystemRepoUpgradeWriter

_TYPE = ".arch-repo/documents/stress-analysis.json"


def _column(declared: dict[str, Any], table: str, name: str) -> dict[str, Any]:
    return next(
        column for section in declared["sections"] for held in section.get("tables", ()) if held["name"] == table
        for column in held["columns"] if column["name"] == name
    )


def _earlier(**architecture: Any) -> dict[str, Any]:
    """The type as a repository holds it from before the columns were typed, adapted where it says."""
    stated = json.loads(json.dumps(STRESS_ANALYSIS_SCHEMA))
    for table, name in (("adaptations", "candidate_architecture"), ("survival", "architecture")):
        column = _column(stated, table, name)
        column.clear()
        column.update({"name": name, "required": True})
    _column(stated, "survival", "architecture").update(architecture)
    stated["frontmatter_schema"]["properties"]["owner-note"] = {"type": "string"}  # the repository's own
    return stated


def _repo(tmp_path: Path, declared: dict[str, Any]) -> Path:
    (tmp_path / ".arch-repo/documents").mkdir(parents=True)
    (tmp_path / _TYPE).write_text(json.dumps(declared, indent=2) + "\n")
    return tmp_path


def _upgraded(root: Path) -> list[str]:
    step = StressAnalysisCandidateColumnsStep()
    view = FilesystemRepoUpgradeView(root)
    return [result.outcome for result in step.apply(view, FilesystemRepoUpgradeWriter(root), step.detect(view))]


def _stored(root: Path) -> dict[str, Any]:
    return json.loads((root / _TYPE).read_text())


def test_both_plain_columns_take_the_shipped_declaration_and_nothing_else_moves(tmp_path: Path) -> None:
    root = _repo(tmp_path, _earlier())

    assert _upgraded(root) == ["applied"]

    stored = _stored(root)
    for table, name in (("adaptations", "candidate_architecture"), ("survival", "architecture")):
        assert _column(stored, table, name) == _column(json.loads(json.dumps(STRESS_ANALYSIS_SCHEMA)), table, name)
    assert stored["frontmatter_schema"]["properties"]["owner-note"] == {"type": "string"}
    assert _upgraded(root) == []


def test_a_column_the_repository_typed_itself_is_left_alone(tmp_path: Path) -> None:
    root = _repo(tmp_path, _earlier(type="string", enum=["naive", "ours"]))  # text, but constrained: still plain
    adapted = _earlier(type="integer")
    other = _repo(tmp_path / "other", adapted)

    assert _upgraded(root) == ["applied"]
    assert _upgraded(other) == ["applied"]
    assert _column(_stored(other), "survival", "architecture") == {"name": "architecture", "required": True,
                                                                   "type": "integer"}
    assert _column(_stored(other), "adaptations", "candidate_architecture")["type"] == "id"


def test_a_current_type_and_a_repository_without_one_have_nothing_to_upgrade(tmp_path: Path) -> None:
    assert _upgraded(_repo(tmp_path, json.loads(json.dumps(STRESS_ANALYSIS_SCHEMA)))) == []
    assert _upgraded(tmp_path / "empty") == []


def test_the_step_is_registered() -> None:
    assert "stress-analysis-candidate-columns" in {step.id for step in DEFAULT_REGISTRY.steps()}

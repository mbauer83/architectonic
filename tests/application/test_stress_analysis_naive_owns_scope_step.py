"""`stress-analysis-naive-owns-scope`: an analysis written while it asked a question and named its scope
diagram is carried into the form where the naive candidate owns the diagram and the document an optional
context — every other byte left as it was, and a second run a no-op."""

from __future__ import annotations

import json
from pathlib import Path

from src.application.change_sets.candidate_recorded_form import dump_candidate, load_candidate
from src.application.repository_upgrade.registry import DEFAULT_REGISTRY
from src.application.repository_upgrade.steps.stress_analysis_naive_owns_scope import StressAnalysisNaiveOwnsScopeStep
from src.domain.repository.repo_default_stress_analysis import STRESS_ANALYSIS_SCHEMA
from src.infrastructure.repository_upgrade.fs_adapter import FilesystemRepoUpgradeView, FilesystemRepoUpgradeWriter
from tests.support.change_sets import candidate

_NAIVE = "CAND@1790000000.Promot.naive"
_DIAGRAM = "ARC@1783185029.4Ayzz3.one-enterprise-repository-many-engagements"
_ANALYSIS = "stress-analyses/STRESS@1790000001.Abcdef.promotion.md"
_BODY = "\n## Naive Architecture\n\nThe promotion path as it stands.\n"


def _earlier_type() -> dict[str, object]:
    stated = json.loads(json.dumps(STRESS_ANALYSIS_SCHEMA))
    properties = stated["frontmatter_schema"]["properties"]
    properties.pop("context")
    properties["question"] = {"type": "string"}
    properties["scope-diagram"] = {"type": "string"}
    properties["owner-note"] = {"type": "string"}  # an adaptation of this repository's own
    return stated


def _analysis(**extra: str) -> str:
    lines = "".join(f"{key}: {value}\n" for key, value in extra.items())
    return (
        f"---\nartifact-id: STRESS@1790000001.Abcdef.promotion\ntitle: Promotion\nstatus: draft\n"
        f"naive-candidate: {_NAIVE}\n{lines}keywords:\n- promotion\n---\n{_BODY}"
    )


def _repo(tmp_path: Path, analysis: str, naive_diagram: str | None = None) -> Path:
    documents = tmp_path / ".arch-repo" / "documents"
    documents.mkdir(parents=True)
    (documents / "stress-analysis.json").write_text(json.dumps(_earlier_type(), indent=2) + "\n")
    (tmp_path / "stress-analyses").mkdir()
    (tmp_path / _ANALYSIS).write_text(analysis)
    (tmp_path / "candidate-architectures").mkdir()
    naive = candidate(id=_NAIVE, name="Naive architecture", diagram=naive_diagram)
    (tmp_path / f"candidate-architectures/{_NAIVE}.candidate.yaml").write_text(dump_candidate(naive))
    return tmp_path


def _upgraded(root: Path) -> list[str]:
    step = StressAnalysisNaiveOwnsScopeStep()
    view = FilesystemRepoUpgradeView(root)
    return [result.outcome for result in step.apply(view, FilesystemRepoUpgradeWriter(root), step.detect(view))]


def _naive(root: Path) -> str | None:
    return load_candidate((root / f"candidate-architectures/{_NAIVE}.candidate.yaml").read_text()).diagram


def test_the_question_becomes_the_context_and_the_scope_diagram_moves_to_the_naive(tmp_path: Path) -> None:
    root = _repo(tmp_path, _analysis(**{"question": "Does promotion hold?", "scope-diagram": _DIAGRAM}))

    assert _upgraded(root) == ["applied", "applied"]

    assert (root / _ANALYSIS).read_text() == _analysis(context="Does promotion hold?")
    assert _naive(root) == _DIAGRAM
    properties = json.loads((root / ".arch-repo/documents/stress-analysis.json").read_text())[
        "frontmatter_schema"]["properties"]
    assert {"context", "owner-note"} <= set(properties)
    assert {"question", "scope-diagram"}.isdisjoint(properties)
    assert StressAnalysisNaiveOwnsScopeStep().detect(FilesystemRepoUpgradeView(root)) == []


def test_a_stated_context_and_a_naive_drawn_elsewhere_are_kept(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        _analysis(**{"question": "Old", "context": "Kept", "scope-diagram": _DIAGRAM}),
        naive_diagram="ARC@1.chosen-later",
    )

    _upgraded(root)

    assert (root / _ANALYSIS).read_text() == _analysis(context="Kept")
    assert _naive(root) == "ARC@1.chosen-later"


def test_an_analysis_whose_naive_is_not_stored_is_reported_and_left(tmp_path: Path) -> None:
    root = _repo(tmp_path, _analysis(**{"scope-diagram": _DIAGRAM}))
    (root / f"candidate-architectures/{_NAIVE}.candidate.yaml").unlink()

    assert sorted(_upgraded(root)) == ["applied", "error"]
    assert "scope-diagram" in (root / _ANALYSIS).read_text()


def test_the_step_is_registered() -> None:
    assert "stress-analysis-naive-owns-scope" in {step.id for step in DEFAULT_REGISTRY.steps()}

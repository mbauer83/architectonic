"""A repository written before renames cascaded still names artifacts by titles they dropped.

Nothing fails because of it — identity is the stem, so every stale reference resolves — which is
precisely why use never repairs it and an upgrade step has to. These cover the two directions that
matter: a former slug is respelled wherever it appears, and a reference that is merely *ambiguous*
or already current is left alone, because retitling a correct reference is the one way this step
could do harm.
"""

from __future__ import annotations

from pathlib import Path

from src.application.repository_upgrade.apply import apply_repository
from src.application.repository_upgrade.evaluate import evaluate_repository
from src.application.repository_upgrade.registry import StepRegistry
from src.application.repository_upgrade.steps.stale_slug_references import StaleSlugReferenceStep
from src.infrastructure.repository_upgrade.fs_adapter import (
    FilesystemRepoUpgradeView,
    FilesystemRepoUpgradeWriter,
)
from tests.support.repository_upgrade_conformance import assert_step_preserves_unknown_content

GOAL = "GOL@1000000001.aBcDeF1.current-title"
OTHER = "REQ@1000000002.gHiJkL2.a-requirement"
FORMER = "GOL@1000000001.aBcDeF1.the-title-it-had"


def _entity(artifact_id: str, artifact_type: str) -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: {artifact_type}
name: An Artifact
extra-unknown-field: keep-me
---

Body.
"""


def _sidecar(source: str, target: str) -> str:
    return f"""\
---
source-entity: {source}
version: 0.1.0
---

<!-- §connections -->

### archimate-realization → {target}

Prose that also cites {target} inline.
"""


def _registry() -> StepRegistry:
    registry = StepRegistry()
    registry.register(StaleSlugReferenceStep())
    return registry


def _setup(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    (tmp_path / ".arch-repo").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _stale_repo(tmp_path: Path) -> Path:
    return _setup(
        tmp_path,
        {
            "model/motivation/goal/g.md": _entity(GOAL, "goal"),
            "model/motivation/requirement/r.md": _entity(OTHER, "requirement"),
            # Written when the goal still carried its former title.
            "model/motivation/requirement/r.outgoing.md": _sidecar(OTHER, FORMER),
        },
    )


class TestAFormerSlugIsRespelled:
    def test_it_is_detected(self, tmp_path: Path) -> None:
        view = FilesystemRepoUpgradeView(_stale_repo(tmp_path))

        findings = StaleSlugReferenceStep().detect(view)

        assert [f.location for f in findings] == ["model/motivation/requirement/r.outgoing.md"]
        assert findings[0].auto_migratable

    def test_every_appearance_is_rewritten(self, tmp_path: Path) -> None:
        """Including the prose citation: a reader is misled by it wherever it sits."""
        root = _stale_repo(tmp_path)
        view, writer = FilesystemRepoUpgradeView(root), FilesystemRepoUpgradeWriter(root)

        apply_repository(view, writer, registry=_registry(), software_version="test")

        healed = (root / "model/motivation/requirement/r.outgoing.md").read_text(encoding="utf-8")
        assert FORMER not in healed
        assert healed.count(GOAL) == 2

    def test_a_second_run_finds_nothing(self, tmp_path: Path) -> None:
        """Detection re-derives from content, so an upgrade may be interrupted and re-run."""
        root = _stale_repo(tmp_path)
        view, writer = FilesystemRepoUpgradeView(root), FilesystemRepoUpgradeWriter(root)
        apply_repository(view, writer, registry=_registry(), software_version="test")

        report = evaluate_repository(FilesystemRepoUpgradeView(root), registry=_registry(), software_version="test")

        assert [r.finding for r in report.results if r.finding.step_id == StaleSlugReferenceStep.id] == []

    def test_it_keeps_content_it_has_no_opinion_about(self, tmp_path: Path) -> None:
        root = _stale_repo(tmp_path)
        location = "model/motivation/requirement/r.outgoing.md"
        (root / location).write_text(
            _sidecar(OTHER, FORMER) + "\nkeep-this-line\n", encoding="utf-8"
        )

        assert_step_preserves_unknown_content(
            StaleSlugReferenceStep(),
            FilesystemRepoUpgradeView(root),
            FilesystemRepoUpgradeWriter(root),
            location=location,
            unknown_marker="keep-this-line",
        )


class TestWhatItMustNotTouch:
    def test_a_current_reference_is_not_a_finding(self, tmp_path: Path) -> None:
        root = _setup(
            tmp_path,
            {
                "model/motivation/goal/g.md": _entity(GOAL, "goal"),
                "model/motivation/requirement/r.md": _entity(OTHER, "requirement"),
                "model/motivation/requirement/r.outgoing.md": _sidecar(OTHER, GOAL),
            },
        )

        assert StaleSlugReferenceStep().detect(FilesystemRepoUpgradeView(root)) == []

    def test_a_stem_two_tiers_both_hold_is_left_alone(self, tmp_path: Path) -> None:
        """With two candidates there is no single current spelling, and guessing retitles a
        reference that may well be the correct one of the two."""
        twin = "GOL@1000000001.aBcDeF1.enterprise-title"
        root = _setup(
            tmp_path,
            {
                "model/motivation/goal/g.md": _entity(GOAL, "goal"),
                "enterprise/model/motivation/goal/g.md": _entity(twin, "goal"),
                "model/motivation/requirement/r.md": _entity(OTHER, "requirement"),
                "model/motivation/requirement/r.outgoing.md": _sidecar(OTHER, FORMER),
            },
        )

        assert StaleSlugReferenceStep().detect(FilesystemRepoUpgradeView(root)) == []

    def test_a_composite_connection_id_keeps_its_separator(self, tmp_path: Path) -> None:
        """The join is three hyphens and a slug may contain hyphens: a rewrite that overran the
        separator would consume the endpoint after it and destroy the id."""
        composite = f"{OTHER}---{FORMER}@@archimate-realization"
        root = _setup(
            tmp_path,
            {
                "model/motivation/goal/g.md": _entity(GOAL, "goal"),
                "model/motivation/requirement/r.md": _entity(OTHER, "requirement"),
                "diagram-catalog/diagrams/d.md": (
                    "---\nartifact-id: ARC@1000000003.mNoPqR3.a-diagram\nartifact-type: diagram\n"
                    f"connection-ids-used:\n- {composite}\n---\n@startuml\n@enduml\n"
                ),
            },
        )
        view, writer = FilesystemRepoUpgradeView(root), FilesystemRepoUpgradeWriter(root)

        apply_repository(view, writer, registry=_registry(), software_version="test")

        healed = (root / "diagram-catalog/diagrams/d.md").read_text(encoding="utf-8")
        assert f"{OTHER}---{GOAL}@@archimate-realization" in healed

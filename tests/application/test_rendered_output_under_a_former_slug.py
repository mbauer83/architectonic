"""Rendered diagram output stranded by a collection rename is moved back under its source.

The defect this repairs was silent for months and surfaced as a refusal that named a step the
reader had already taken: the PNG download answered ``404 PNG not yet rendered — save the diagram
first`` for every diagram in a renamed collection, while the SVG route — which re-derives on read —
answered 200 throughout. The rename had moved ``diagrams/<slug>/`` and left ``rendered/<slug>/``
behind.

The step derives where each picture belongs from where its source sits now, never from a record of
the rename, so it repairs output stranded by a rename nobody wrote down.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.repository_upgrade.steps.rendered_output_collection import (
    RenderedOutputCollectionStep,
)
from src.infrastructure.repository_upgrade.fs_adapter import (
    FilesystemRepoUpgradeView,
    FilesystemRepoUpgradeWriter,
)

CATALOG = "diagram-catalog"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "architecture-repository"
    (root / CATALOG / "diagrams").mkdir(parents=True)
    (root / CATALOG / "rendered").mkdir(parents=True)
    return root


def _write(root: Path, relative: str, content: bytes = b"x") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _run(repo: Path) -> list[str]:
    """Detect and apply, returning the locations reported as applied."""
    step = RenderedOutputCollectionStep()
    view = FilesystemRepoUpgradeView(root=repo)
    findings = step.detect(view)
    applied = step.apply(view, FilesystemRepoUpgradeWriter(root=repo), findings)
    return [result.finding.location for result in applied if result.outcome == "applied"]


class TestOutputLeftUnderAFormerSlug:
    def test_both_rendered_forms_follow_the_source(self, repo: Path) -> None:
        _write(repo, f"{CATALOG}/diagrams/new-name/ARC@1.abc.a-diagram.puml", b"@startuml\n@enduml\n")
        for suffix in (".png", ".svg"):
            _write(repo, f"{CATALOG}/rendered/old-name/ARC@1.abc.a-diagram{suffix}")

        moved = _run(repo)

        assert len(moved) == 2
        for suffix in (".png", ".svg"):
            assert (repo / CATALOG / "rendered" / "new-name" / f"ARC@1.abc.a-diagram{suffix}").exists(), suffix
        assert not (repo / CATALOG / "rendered" / "old-name").exists()

    def test_the_finding_says_what_the_reader_would_have_seen(self, repo: Path) -> None:
        _write(repo, f"{CATALOG}/diagrams/new-name/ARC@1.abc.a-diagram.puml", b"@startuml\n@enduml\n")
        _write(repo, f"{CATALOG}/rendered/old-name/ARC@1.abc.a-diagram.png")

        findings = RenderedOutputCollectionStep().detect(FilesystemRepoUpgradeView(root=repo))

        assert len(findings) == 1
        assert findings[0].auto_migratable
        assert "404" in findings[0].description
        assert "rendered/new-name" in (findings[0].rewrite_summary or "")

    def test_a_rendering_that_is_where_it_belongs_is_not_touched(self, repo: Path) -> None:
        _write(repo, f"{CATALOG}/diagrams/a-collection/ARC@1.abc.a-diagram.puml", b"@startuml\n@enduml\n")
        settled = _write(repo, f"{CATALOG}/rendered/a-collection/ARC@1.abc.a-diagram.png")
        before = settled.stat().st_mtime_ns

        assert _run(repo) == []
        assert settled.stat().st_mtime_ns == before

    def test_applying_twice_changes_nothing_the_second_time(self, repo: Path) -> None:
        """`--commit` may be interrupted and re-run, so every step has to be idempotent."""
        _write(repo, f"{CATALOG}/diagrams/new-name/ARC@1.abc.a-diagram.puml", b"@startuml\n@enduml\n")
        _write(repo, f"{CATALOG}/rendered/old-name/ARC@1.abc.a-diagram.png")

        assert len(_run(repo)) == 1
        assert _run(repo) == []


class TestWhatItMustNotMove:
    def test_confidential_output_stays_where_it_is(self, repo: Path) -> None:
        """It is filed flat, with no slug segment, so a rename never strands it."""
        _write(repo, f"{CATALOG}/diagrams/confidential/a-collection/ARC@1.abc.secret.puml", b"@startuml\n@enduml\n")
        _write(repo, f"{CATALOG}/rendered/confidential/ARC@1.abc.secret.png")

        assert _run(repo) == []
        assert (repo / CATALOG / "rendered" / "confidential" / "ARC@1.abc.secret.png").exists()

    def test_a_rendering_whose_diagram_is_gone_is_left_alone(self, repo: Path) -> None:
        """There is nowhere to file it, and deleting a repository's content is not this step's call."""
        orphan = _write(repo, f"{CATALOG}/rendered/old-name/ARC@1.abc.deleted.png")

        assert _run(repo) == []
        assert orphan.exists()

    def test_an_ambiguous_stem_is_left_alone(self, repo: Path) -> None:
        """Two sources with one stem give no single answer, and a guess files it under the wrong one."""
        for collection in ("one", "two"):
            _write(repo, f"{CATALOG}/diagrams/{collection}/ARC@1.abc.a-diagram.puml", b"@startuml\n@enduml\n")
        stranded = _write(repo, f"{CATALOG}/rendered/old-name/ARC@1.abc.a-diagram.png")

        assert _run(repo) == []
        assert stranded.exists()

    def test_a_file_that_is_not_a_rendering_is_left_alone(self, repo: Path) -> None:
        _write(repo, f"{CATALOG}/diagrams/new-name/ARC@1.abc.a-diagram.puml", b"@startuml\n@enduml\n")
        note = _write(repo, f"{CATALOG}/rendered/old-name/README.md")

        assert _run(repo) == []
        assert note.exists()


class TestTheLegacyLayout:
    def test_a_diagram_directly_under_diagrams_renders_to_the_rendered_root(self, repo: Path) -> None:
        """Pinned so the repair does not file a legacy repository's output into a collection."""
        _write(repo, f"{CATALOG}/diagrams/ARC@1.abc.a-diagram.puml", b"@startuml\n@enduml\n")
        settled = _write(repo, f"{CATALOG}/rendered/ARC@1.abc.a-diagram.png")

        assert _run(repo) == []
        assert settled.exists()

    def test_output_under_a_slug_moves_to_the_root_when_its_source_is_legacy(self, repo: Path) -> None:
        _write(repo, f"{CATALOG}/diagrams/ARC@1.abc.a-diagram.puml", b"@startuml\n@enduml\n")
        _write(repo, f"{CATALOG}/rendered/old-name/ARC@1.abc.a-diagram.png")

        assert len(_run(repo)) == 1
        assert (repo / CATALOG / "rendered" / "ARC@1.abc.a-diagram.png").exists()

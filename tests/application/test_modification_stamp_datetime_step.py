"""Upgrading a repository's date-only `last-updated` stamps to full UTC datetimes.

The properties worth pinning are the destructive ones. A migration that re-stamped to "now"
would erase the only record of when an artifact last changed; a migration that reparsed and
re-dumped the frontmatter would reorder keys and drop comments; a migration that guessed at an
unparseable value would silently invent a modification date. And running it twice must change
nothing, because the upgrade framework may run it against an already-migrated repo.
"""

from __future__ import annotations

from pathlib import Path

from src.application.artifact_parsing import extract_yaml_block
from src.application.repository_upgrade.steps.modification_stamp_datetime import (
    ModificationStampDatetimeStep,
)
from src.infrastructure.repository_upgrade.fs_adapter import (
    FilesystemRepoUpgradeView,
    FilesystemRepoUpgradeWriter,
)
from tests.support.repository_upgrade_conformance import assert_step_preserves_unknown_content

_QUOTED_DATE = """\
---
artifact-id: REQ@1.abc.quoted
artifact-type: requirement
name: Quoted Date
version: 0.1.0
status: draft
last-updated: '2026-01-01'
keywords: [alpha]
---

<!-- §content -->

## Quoted Date

Body.
"""

_UNQUOTED_DATE = """\
---
artifact-id: ARC@1.abc.unquoted
artifact-type: diagram
name: Unquoted Date
diagram-type: archimate-motivation
last-updated: 2026-02-03
---
@startuml
@enduml
"""

_ALREADY_DATETIME = """\
---
artifact-id: ADR@1.abc.current
artifact-type: document
doc-type: adr
title: Already Current
status: draft
last-updated: '2026-07-24T09:15:00Z'
---

## Context

Text.
"""

_MALFORMED = """\
---
source-entity: REQ@1.abc.src
version: 0.1.0
status: draft
last-updated: whenever
---
### realization → APP@1.abc.target

Description.
"""

_NO_STAMP = """\
---
artifact-id: REQ@1.abc.bare
artifact-type: requirement
name: Bare
---
body
"""


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _fixture_repo(root: Path) -> FilesystemRepoUpgradeView:
    (root / ".arch-repo").mkdir(parents=True, exist_ok=True)
    _write(root, "model/motivation/requirement/REQ@1.abc.quoted.md", _QUOTED_DATE)
    _write(root, "diagram-catalog/diagrams/motivation/ARC@1.abc.unquoted.puml", _UNQUOTED_DATE)
    _write(root, "docs/adr/ADR@1.abc.current.md", _ALREADY_DATETIME)
    _write(root, "model/motivation/requirement/REQ@1.abc.src.outgoing.md", _MALFORMED)
    _write(root, "model/motivation/requirement/REQ@1.abc.bare.md", _NO_STAMP)
    return FilesystemRepoUpgradeView(root)


def _stamp_of(root: Path, rel: str) -> object:
    frontmatter = extract_yaml_block((root / rel).read_text(encoding="utf-8"))
    assert frontmatter is not None
    return frontmatter.get("last-updated")


def _apply_all(root: Path) -> FilesystemRepoUpgradeView:
    step = ModificationStampDatetimeStep()
    view = FilesystemRepoUpgradeView(root)
    writer = FilesystemRepoUpgradeWriter(root)
    findings = [f for f in step.detect(view) if f.auto_migratable]
    step.apply(view, writer, findings)
    return view


class TestDetect:
    def test_fires_for_date_only_stamps_quoted_and_unquoted(self, tmp_path: Path) -> None:
        findings = ModificationStampDatetimeStep().detect(_fixture_repo(tmp_path))

        migratable = sorted(f.location for f in findings if f.auto_migratable)
        assert migratable == [
            "diagram-catalog/diagrams/motivation/ARC@1.abc.unquoted.puml",
            "model/motivation/requirement/REQ@1.abc.quoted.md",
        ]

    def test_reports_an_unreadable_stamp_for_a_human_instead_of_guessing(self, tmp_path: Path) -> None:
        findings = ModificationStampDatetimeStep().detect(_fixture_repo(tmp_path))

        manual = [f for f in findings if not f.auto_migratable]
        assert [f.location for f in manual] == ["model/motivation/requirement/REQ@1.abc.src.outgoing.md"]
        assert manual[0].severity == "warning"
        assert manual[0].manual_instructions

    def test_silent_on_current_and_unstamped_artifacts(self, tmp_path: Path) -> None:
        findings = ModificationStampDatetimeStep().detect(_fixture_repo(tmp_path))

        touched = {f.location for f in findings}
        assert "docs/adr/ADR@1.abc.current.md" not in touched
        assert "model/motivation/requirement/REQ@1.abc.bare.md" not in touched

    def test_rewrite_summary_names_the_preserved_date(self, tmp_path: Path) -> None:
        findings = ModificationStampDatetimeStep().detect(_fixture_repo(tmp_path))

        summary = next(f.rewrite_summary for f in findings if f.location.endswith("REQ@1.abc.quoted.md"))
        assert summary is not None
        assert "2026-01-01T00:00:00Z" in summary


class TestApply:
    def test_preserves_the_historic_date_rather_than_re_stamping_to_now(self, tmp_path: Path) -> None:
        _fixture_repo(tmp_path)
        _apply_all(tmp_path)

        assert _stamp_of(tmp_path, "model/motivation/requirement/REQ@1.abc.quoted.md") == "2026-01-01T00:00:00Z"
        assert (
            _stamp_of(tmp_path, "diagram-catalog/diagrams/motivation/ARC@1.abc.unquoted.puml")
            == "2026-02-03T00:00:00Z"
        )

    def test_leaves_an_unreadable_stamp_untouched(self, tmp_path: Path) -> None:
        _fixture_repo(tmp_path)
        _apply_all(tmp_path)

        assert _stamp_of(tmp_path, "model/motivation/requirement/REQ@1.abc.src.outgoing.md") == "whenever"

    def test_preserves_key_order_and_the_rest_of_the_file(self, tmp_path: Path) -> None:
        _fixture_repo(tmp_path)
        rel = "model/motivation/requirement/REQ@1.abc.quoted.md"
        before = (tmp_path / rel).read_text(encoding="utf-8")

        _apply_all(tmp_path)

        after = (tmp_path / rel).read_text(encoding="utf-8")
        assert after == before.replace("last-updated: '2026-01-01'", "last-updated: '2026-01-01T00:00:00Z'")

    def test_running_twice_changes_nothing(self, tmp_path: Path) -> None:
        _fixture_repo(tmp_path)
        _apply_all(tmp_path)
        after_first = {
            path.relative_to(tmp_path).as_posix(): path.read_text(encoding="utf-8")
            for path in sorted(tmp_path.rglob("*.md")) + sorted(tmp_path.rglob("*.puml"))
        }

        step = ModificationStampDatetimeStep()
        view = FilesystemRepoUpgradeView(tmp_path)
        second_pass = [f for f in step.detect(view) if f.auto_migratable]
        assert second_pass == []

        _apply_all(tmp_path)
        after_second = {
            path.relative_to(tmp_path).as_posix(): path.read_text(encoding="utf-8")
            for path in sorted(tmp_path.rglob("*.md")) + sorted(tmp_path.rglob("*.puml"))
        }
        assert after_second == after_first

    def test_the_migrated_stamp_reads_back_canonically(self, tmp_path: Path) -> None:
        _fixture_repo(tmp_path)
        _apply_all(tmp_path)

        from src.application.artifact_parsing import _canonical_stamp

        stamp = _stamp_of(tmp_path, "model/motivation/requirement/REQ@1.abc.quoted.md")
        assert _canonical_stamp(stamp) == "2026-01-01T00:00:00Z"

    def test_carries_unrelated_content_forward(self, tmp_path: Path) -> None:
        (tmp_path / ".arch-repo").mkdir(parents=True, exist_ok=True)
        rel = "model/motivation/requirement/REQ@1.abc.quoted.md"
        _write(tmp_path, rel, _QUOTED_DATE.replace("keywords: [alpha]", "keywords: [alpha]\nlocal-draft-note: keep me"))

        assert_step_preserves_unknown_content(
            ModificationStampDatetimeStep(),
            FilesystemRepoUpgradeView(tmp_path),
            FilesystemRepoUpgradeWriter(tmp_path),
            location=rel,
            unknown_marker="local-draft-note: keep me",
        )

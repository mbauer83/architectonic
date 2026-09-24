"""One reading of which kind of artifact a repository path holds, and nothing outside the layout is one."""

from __future__ import annotations

import pytest

from src.domain.repository.artifact_location import artifact_kind_at


@pytest.mark.parametrize(
    ("relative", "kind"),
    [
        ("model/application/application-component/APP@1.a.x.md", "entity"),
        ("projects/core/model/application/application-component/APP@1.a.x.md", "entity"),
        ("model/application/application-component/APP@1.a.x.outgoing.md", "connection"),
        ("projects/core/model/motivation/goal/GOL@1.a.x.outgoing.md", "connection"),
        ("docs/adr/core/ADR@1.a.x.md", "document"),
        ("diagram-catalog/diagrams/core/ARC@1.a.x.puml", "diagram"),
        ("diagram-catalog/diagrams/core/MTX@1.a.x.md", "diagram"),
        ("diagram-catalog/diagrams/confidential/STPA@1.a.x.puml", "diagram"),
        ("scratchpads/core/SCR@1.a.x.scratchpad.yaml", "scratchpad"),
    ],
)
def test_each_artifact_source_is_read_by_where_it_sits(relative: str, kind: str) -> None:
    assert artifact_kind_at(relative) == kind


@pytest.mark.parametrize(
    "relative",
    [
        "README.md",
        "model",
        "model/README.txt",
        "projects/core/README.md",
        "projects/core/model",
        "projects/core/docs/x.md",
        "docs/adr/core/diagram.png",
        "diagram-catalog/_archimate-glyphs.puml",
        "diagram-catalog/rendered/core/ARC@1.a.x.svg",
        "diagram-catalog/icons/ICO@1.a.x.md",
        "diagram-catalog/diagrams/core/ARC@1.a.x.svg",
        "scratchpads/core/notes.yaml",
        ".arch-repo/documents/adr.json",
        "connections/APP@1.a.x.md",
    ],
)
def test_a_path_outside_the_layout_holds_no_artifact(relative: str) -> None:
    assert artifact_kind_at(relative) is None


def test_a_windows_style_relative_path_reads_the_same() -> None:
    from pathlib import PureWindowsPath

    assert artifact_kind_at(PureWindowsPath(r"projects\core\model\a\b\APP@1.a.x.md")) == "entity"

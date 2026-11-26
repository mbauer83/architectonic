"""The diagrams a repository holds, read for a step: which files are diagrams, and what each states.

One reading for the steps that rewrite a diagram's frontmatter, so they agree on what a diagram file is.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from src.application.artifacts.parsing import extract_yaml_block
from src.application.repository_upgrade.ports import RepoUpgradeView
from src.application.repository_upgrade.steps._frontmatter_scan import list_frontmatter_candidate_files
from src.domain.repository.frontmatter import opens_with_frontmatter


@dataclass(frozen=True)
class DiagramFile:
    """One diagram file: where it is, its text, and its frontmatter as a mapping."""

    location: str
    content: str
    frontmatter: dict[str, object]


def diagram_frontmatter(content: str | None) -> dict[str, object] | None:
    """The frontmatter of *content* when it is a diagram's, else None."""
    if content is None or not opens_with_frontmatter(content):
        return None
    frontmatter = extract_yaml_block(content)
    if not isinstance(frontmatter, dict) or str(frontmatter.get("artifact-type", "")) != "diagram":
        return None
    return frontmatter


def diagram_files(view: RepoUpgradeView) -> Iterator[DiagramFile]:
    """Every diagram the repository behind *view* holds."""
    for location in list_frontmatter_candidate_files(view):
        content = view.read_text(location)
        frontmatter = diagram_frontmatter(content)
        if content is not None and frontmatter is not None:
            yield DiagramFile(location, content, frontmatter)

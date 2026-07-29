"""Shared file-discovery helper for steps that scan frontmatter-bearing content.

Content *extensions*, not directories, are hardcoded here — deliberately. Directory layout
varies (a top-level `model/`+`diagram-catalog/` AND per-project `projects/*/model/`+
`projects/*/diagram-catalog/` can both exist in the same repo — the recurring
"hardcoded-directory-list" bug family this project has hit before), so every glob here is
`**/*.<ext>`, recursive from the repo root, with no directory assumed at all. Extensions
currently in real use: `.md` (entities, connections, documents, matrix-type diagrams) and
`.puml` (PlantUML-rendered diagram types — ArchiMate, sequence, activity, c4, ...). Add a
glob here, not per-step, if a future diagram type introduces another source extension.
"""

from __future__ import annotations

from src.application.repository_upgrade.ports import RepoUpgradeView

_FRONTMATTER_BEARING_GLOBS = ("**/*.md", "**/*.puml")


def list_frontmatter_candidate_files(view: RepoUpgradeView) -> list[str]:
    seen: set[str] = set()
    for glob in _FRONTMATTER_BEARING_GLOBS:
        seen.update(view.list_files(glob))
    return sorted(seen)

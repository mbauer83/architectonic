"""W046 — content filed under a group the registry does not declare.

Registered into `_GENERIC_REPOSITORY_CONTRIBUTIONS` on import, the same mechanism as W044 and E335.

`artifact_create_entity(group="payments")` writes `projects/payments/model/…` whether or not
`payments` is a declared model project — the group is a property of the path, and the path is valid
either way. Verification passed on every such file, so entities could accumulate for weeks in a
directory the GUI's model navigation had nothing to list them under: reachable by search and by id,
absent from everywhere a person browses. A repository can say this about itself, and now does.

Two things this rule deliberately does not do.

It does not read `ctx.candidate`. On the `verify_all` path the candidate is a
`RegistryOnlyCandidateRepository` whose `list_*` answer `[]` by design — a rule enumerating content
through it would be silent in the product and green in a test that supplied a real store instead.

It does not derive a slug from a path itself. `group_fn` owns that for all three families, including
the legacy layouts and the confidential nesting, and a second reading of the same directory shapes is
how the two come to disagree. This walks the files and asks it.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from src.application.repo_path_helpers import diagram_source_root, docs_root, group_fn
from src.domain.repository.groups import UNCATEGORIZED, GroupAxis
from src.domain.repository.repo_layout import PROJECTS

#: Each axis, the root beneath which its groups' content lives, and what to call that content in a
#: finding. The roots come from the path helpers rather than being spelled here.
_AXES: tuple[tuple[GroupAxis, Any, str], ...] = (
    ("model-project", lambda root: root / PROJECTS, "model file"),
    ("diagram-collection", diagram_source_root, "diagram"),
    ("document-collection", docs_root, "document"),
)


def _artifact_files(root: Path) -> Iterator[Path]:
    return (path for path in root.rglob("*.md") if path.is_file())


def _tally(repo_root: Path, axis_root: Path) -> dict[str, int]:
    """How many artifact files sit under each group slug beneath `axis_root`."""
    counts: dict[str, int] = {}
    for path in _artifact_files(axis_root):
        slug = group_fn(path, repo_root)
        if slug and slug != UNCATEGORIZED:
            counts[slug] = counts.get(slug, 0) + 1
    return counts


class UndeclaredGroupContribution:
    """W046: artifacts filed under a slug their axis does not declare."""

    diagnostic_codes: tuple[str, ...] = ("W046",)

    def run(self, ctx: Any, result: Any) -> None:
        from src.application.group_registry import load_group_registry  # noqa: PLC0415
        from src.application.verification.artifact_verifier_types import Issue, Severity  # noqa: PLC0415

        repo_root = Path(ctx.location)
        registry = load_group_registry(repo_root)
        for axis, root_of, noun in _AXES:
            axis_root = root_of(repo_root)
            if not axis_root.exists():
                continue
            counts = _tally(repo_root, axis_root)
            for slug in sorted(counts):
                if registry.is_valid_target(axis, slug):
                    continue
                held = counts[slug]
                result.issues.append(
                    Issue(
                        Severity.WARNING,
                        "W046",
                        f"Group '{slug}' holds {held} {noun}{'' if held == 1 else 's'} but is not "
                        f"declared as a {axis}; navigation cannot reach them",
                        ctx.location,
                    )
                )


_W046_SINGLETON = UndeclaredGroupContribution()

from src.domain.diagrams.diagram_verification import _GENERIC_REPOSITORY_CONTRIBUTIONS  # noqa: E402

if not any(isinstance(c, UndeclaredGroupContribution) for c in _GENERIC_REPOSITORY_CONTRIBUTIONS):
    _GENERIC_REPOSITORY_CONTRIBUTIONS.append(_W046_SINGLETON)

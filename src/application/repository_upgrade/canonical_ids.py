"""How an artifact is spelled *now*, read from the repository itself.

An artifact's own frontmatter is the only authority on its current id: every other appearance of that
id is a reference, and a reference is exactly what may have gone stale. So the canonical index is
built from `artifact-id` declarations and nothing else.

Both upgrade families need it, which is why it is not inside either. The repository step respells
references in repository files; the operational step respells the confidential store's architecture
references, whose current spelling lives in a repository the store deliberately cannot read
(ADR@1783406789 — the closed tier holds one-way references into architecture). The CLI owns the join,
and hands the index to the step, rather than either side reaching across the boundary.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.application.artifacts.parsing import extract_yaml_block
from src.application.repository_upgrade.ports import RepoUpgradeView
from src.application.repository_upgrade.steps._frontmatter_scan import list_frontmatter_candidate_files
from src.domain.artifact_id import canonical_ids_by_stem, is_entity_id, stable_id
from src.domain.repository.frontmatter import opens_with_frontmatter


def declared_artifact_ids(view: RepoUpgradeView) -> list[str]:
    """Every id an artifact declares for itself, across one repo root."""
    declared: list[str] = []
    for rel in list_frontmatter_candidate_files(view):
        content = view.read_text(rel)
        if content is None or not opens_with_frontmatter(content):
            continue
        frontmatter = extract_yaml_block(content)
        if not isinstance(frontmatter, dict):
            continue
        artifact_id = str(frontmatter.get("artifact-id") or "").strip()
        if artifact_id and is_entity_id(artifact_id):
            declared.append(artifact_id)
    return declared


def canonical_index(views: Iterable[RepoUpgradeView]) -> dict[str, set[str]]:
    """Stem → every current spelling carrying it, across every repo root being upgraded.

    A set, not a value: the engagement and enterprise tiers can each hold an artifact with the same
    stem, and with two candidates there is no single current spelling — respelling to a guess would
    retitle a reference that may already be the correct one.
    """
    return canonical_ids_by_stem(
        (artifact_id for view in views for artifact_id in declared_artifact_ids(view)),
        stem_of=stable_id,
    )

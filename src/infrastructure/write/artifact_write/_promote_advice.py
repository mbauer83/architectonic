"""The advice open on what a promotion would carry to the enterprise.

Promotion is where an element stops being one team's draft and becomes what others build on, so the
dry run is where its open advice is shown — beside the plan, never in `schema_errors`: advice never
blocks a promotion. An element that acknowledged an advice carries no finding here, only its
acknowledgement, which travels with it in its frontmatter.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.application.artifacts.query import ArtifactRepository
from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.verification.advice_report import element_advice
from src.domain.verification_findings import Issue


def promotion_advice(entity_ids: Iterable[str], repo: ArtifactRepository, catalogs: RuntimeCatalogs) -> list[Issue]:
    """Each open advice on the entities *entity_ids*, in their order, read off the index."""
    records = (repo.get_entity(entity_id) for entity_id in dict.fromkeys(entity_ids))
    return [issue for record in records if record is not None for issue in element_advice(record, repo, catalogs).open]

"""Pure matching, indexing, and partitioning helpers for :func:`plan_promotion`.

These contain no promotion side effects and no dependency on the plan/conflict
dataclasses, so they stay trivially testable and free of import cycles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.application.artifact_query import ArtifactRepository
from src.application.verification.artifact_verifier import ArtifactRegistry
from src.domain.artifact_id import stable_id
from src.infrastructure.write.artifact_write.parse_existing import parse_entity_file


@dataclass(frozen=True)
class ClassifierIndexes:
    """Enterprise workspace classifier ids indexed for same-id and name-clash detection."""

    by_id: frozenset[str]          # enterprise classifier artifact_ids (CLF@…)
    by_name: dict[str, str]        # normalized_name → first-seen enterprise clf_id


def _normalize_classifier_name(name: str) -> str:
    return name.strip().lower()


def build_enterprise_classifier_indexes(
    repo: ArtifactRepository, registry: ArtifactRegistry
) -> ClassifierIndexes:
    """Build name and id indexes of all enterprise workspace classifiers."""
    enterprise_ids = registry.enterprise_entity_ids()
    clf_ids: set[str] = {eid for eid in enterprise_ids if eid.startswith("CLF@")}
    by_name: dict[str, str] = {}
    for clf_id in clf_ids:
        rec = repo.get_entity(clf_id)
        if rec is not None:
            norm = _normalize_classifier_name(rec.name)
            if norm not in by_name:
                by_name[norm] = clf_id
    return ClassifierIndexes(by_id=frozenset(clf_ids), by_name=by_name)


def _extract_id_suffix(artifact_id: str) -> str | None:
    """Return the portion after '@' (epoch.random), or None if the ID has no '@'."""
    return artifact_id.split("@", 1)[1] if "@" in artifact_id else None


def _parse_conn_full(cid: str) -> tuple[str, str, str] | None:
    if "---" in cid and "@@" in cid:
        source, rest = cid.split("---", 1)
        target, conn_type = rest.rsplit("@@", 1)
        if source and target and conn_type:
            return source.strip(), conn_type.strip(), target.strip()
    if " → " not in cid:
        return None
    left, target = cid.rsplit(" → ", 1)
    parts = left.split(" ", 1)
    if len(parts) < 2:
        return None
    return (parts[0].strip(), parts[1].strip(), target.strip())


def _normalize_name(name: str) -> str:
    return name.strip().lower().replace("-", " ").replace("_", " ")


def _build_enterprise_name_index(repo: ArtifactRepository, registry: ArtifactRegistry) -> dict[tuple[str, str], Any]:
    return {
        (rec.artifact_type, _normalize_name(rec.name)): rec
        for eid in registry.enterprise_entity_ids()
        if (rec := repo.get_entity(eid)) is not None
    }


def _build_enterprise_id_suffix_index(
    repo: ArtifactRepository, registry: ArtifactRegistry
) -> dict[tuple[str, str], Any]:
    """Index enterprise entities by (artifact_type, id_suffix) to catch same-ID renames."""
    index: dict[tuple[str, str], Any] = {}
    for eid in registry.enterprise_entity_ids():
        rec = repo.get_entity(eid)
        if rec is not None and (suffix := _extract_id_suffix(eid)) is not None:
            index[(rec.artifact_type, suffix)] = rec
    return index


def _entity_frontmatter(registry: ArtifactRegistry, eid: str) -> dict[str, Any]:
    path = registry.find_file_by_id(eid)
    if path is None:
        return {}
    try:
        return dict(parse_entity_file(path).frontmatter)
    except Exception:  # noqa: BLE001
        return {}


def _partition_selected(
    selected_ids: list[str], *, enterprise_ids: set[str], gar_ids: set[str], warnings: list[str]
) -> tuple[list[str], list[str]]:
    """Split the selection into entities already promoted and fresh candidates (GARs skipped)."""
    enterprise_short = {stable_id(e) for e in enterprise_ids}
    gar_short = {stable_id(e) for e in gar_ids}
    already: list[str] = []
    candidates: list[str] = []
    for eid in selected_ids:
        eid_short = stable_id(eid)
        if eid_short in enterprise_short:
            already.append(eid)
        elif eid_short in gar_short:
            warnings.append(f"Skipped GAR {eid} from promotion set")
        else:
            candidates.append(eid)
    return already, candidates


def _match_enterprise(
    rec: Any, eid: str, name_index: dict[tuple[str, str], Any], suffix_index: dict[tuple[str, str], Any]
) -> Any | None:
    """Match an engagement entity to an enterprise one by name, then by id-suffix (rename-safe)."""
    ent_rec = name_index.get((rec.artifact_type, _normalize_name(rec.name)))
    if ent_rec is None and (suffix := _extract_id_suffix(eid)) is not None:
        ent_rec = suffix_index.get((rec.artifact_type, suffix))
    return ent_rec


def _collect_promotable_connections(
    registry: ArtifactRegistry, *, promotable: set[str], selected_set: set[str], explicit_connection_ids: set[str]
) -> list[str]:
    """Connections whose source is promotable and target is an explicitly selected, requested edge."""
    conn_ids: list[str] = []
    for cid in registry.connection_ids():
        parsed = _parse_conn_full(cid)
        if parsed is None:
            continue
        src, _conn_type, tgt = parsed
        if src in promotable and tgt in selected_set and cid in explicit_connection_ids:
            conn_ids.append(cid)
    return conn_ids

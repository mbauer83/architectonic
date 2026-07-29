"""Type-closure computation for datatype diagram promotion.

When promoting diagrams, any classifier referenced by an attribute type must have
its host diagram promoted too. This module derives that closure from the set of
diagrams being promoted.

Stage 1 (planning): ``compute_type_closure`` returns required host-diagram additions
and classifier ids whose host cannot be found (blocking broken-closure condition).
Stage 2 (verify): the enterprise-only ``collect_verification_errors(root, include_diagrams=True)``
implicitly re-validates after conflict resolutions are applied.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TypeClosureResult:
    additions: list[str] = field(default_factory=list)
    reasons: dict[str, str] = field(default_factory=dict)
    broken: list[str] = field(default_factory=list)


def _extract_classifier_refs(extra: Any) -> list[str]:
    """Return CLF@ ids referenced as classifier attribute types in diagram extra."""
    if not isinstance(extra, dict):
        return []
    raw_de: object = extra.get("diagram-entities")
    de: dict = raw_de if isinstance(raw_de, dict) else {}
    refs: list[str] = []
    for clf in de.get("classifier") or []:
        if not isinstance(clf, dict):
            continue
        for attr in clf.get("attributes") or []:
            if not isinstance(attr, dict):
                continue
            t = attr.get("type")
            if isinstance(t, dict) and t.get("kind") == "classifier":
                clf_id = str(t.get("id") or "")
                if clf_id.startswith("CLF@"):
                    refs.append(clf_id)
    return refs


def compute_type_closure(
    diagram_ids: list[str],
    repo: Any,
    registry: Any,
) -> TypeClosureResult:
    """Derive host-diagram additions required for classifier type references to resolve.

    For each datatype diagram in ``diagram_ids``, inspects classifier attribute type
    refs. For each ``{kind:classifier, id:CLF@…}`` ref, looks up the defining host
    diagram. If that host is not already in the promotion set or enterprise, it is
    added to ``additions``. Classifiers with no discoverable host go to ``broken``.
    """
    enterprise_diag_ids: set[str] = registry.enterprise_diagram_ids()
    promotion_set: set[str] = set(diagram_ids)
    result = TypeClosureResult()
    seen_clf: set[str] = set()

    for did in diagram_ids:
        diag = repo.get_diagram(did)
        if diag is None or getattr(diag, "diagram_type", None) != "datatype":
            continue
        for clf_id in _extract_classifier_refs(getattr(diag, "extra", None)):
            if clf_id in seen_clf:
                continue
            seen_clf.add(clf_id)
            rec = repo.find_entity_by_workspace_id(clf_id)
            if rec is None or not getattr(rec, "host_diagram_id", None):
                result.broken.append(clf_id)
                continue
            host = rec.host_diagram_id
            if host in promotion_set or host in enterprise_diag_ids:
                continue
            promotion_set.add(host)
            result.additions.append(host)
            result.reasons[host] = (
                f"required to host classifier {clf_id} referenced in {did}"
            )

    return result

"""Datatype key + generalization-set verification contributions (E337/E338/E339).

Structural rules over diagram-owned data:
- E337/E338 — identity (composite primary key) and unique_keys must reference valid,
  distinct attribute ids declared by the same classifier.
- E339 — every generalization_set reference resolves and groups a single general
  (target) classifier across its dt-generalization relationships.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from src.domain.diagrams.diagram_verification import BaseDiagramVerificationContext


def _own_attribute_ids(classifier: dict[str, Any]) -> set[str]:
    attributes = classifier.get("attributes")
    return {
        str(attr.get("id") or "")
        for attr in (attributes if isinstance(attributes, list) else [])
        if isinstance(attr, dict) and str(attr.get("id") or "")
    }


def _key_member_error(members: object, attr_ids: set[str]) -> str | None:
    """Validate distinctness and resolution of a key's attribute-id list (non-emptiness aside)."""
    if not isinstance(members, list):
        return "must be a list of attribute ids"
    ids = [str(m) for m in members]
    if any(not i for i in ids):
        return "contains an empty attribute reference"
    if len(ids) != len(set(ids)):
        return "contains duplicate attributes"
    missing = sorted(set(ids) - attr_ids)
    return f"references unknown attribute id(s): {missing}" if missing else None


class _KeyConstraintContribution:
    """E337/E338 — identity and unique_keys reference valid, distinct own-attribute ids.

    E338: the identity (composite primary key) is malformed.
    E337: a unique key is empty or malformed.
    """

    diagnostic_codes: tuple[str, ...] = ("E337", "E338")

    def run(self, candidate: Any, ctx: BaseDiagramVerificationContext, result: Any) -> None:
        del candidate
        from src.domain.verification_findings import Issue, Severity  # noqa: PLC0415

        de = ctx.fm.get("diagram-entities")
        classifiers = de.get("classifier") if isinstance(de, dict) else None
        for classifier in classifiers if isinstance(classifiers, list) else []:
            if not isinstance(classifier, dict):
                continue
            clf_id = str(classifier.get("id") or "")
            attr_ids = _own_attribute_ids(classifier)

            identity = classifier.get("identity")
            if isinstance(identity, list) and identity:
                error = _key_member_error(identity, attr_ids)
                if error is not None:
                    result.issues.append(Issue(
                        Severity.ERROR, "E338",
                        f"Classifier '{clf_id}' identity: {error}", ctx.loc,
                    ))

            for index, key in enumerate(classifier.get("unique_keys") or []):
                members = key.get("attribute_ids") if isinstance(key, dict) else None
                error = (
                    "must contain at least one attribute"
                    if not isinstance(members, list) or not members
                    else _key_member_error(members, attr_ids)
                )
                if error is not None:
                    result.issues.append(Issue(
                        Severity.ERROR, "E337",
                        f"Classifier '{clf_id}' unique key {index + 1}: {error}", ctx.loc,
                    ))


KEY_CONSTRAINT_CONTRIBUTION = _KeyConstraintContribution()


def _declared_set_ids(de: object) -> set[str]:
    sets = de.get("generalization_set") if isinstance(de, dict) else None
    return {
        str(s.get("id") or "")
        for s in (sets if isinstance(sets, list) else [])
        if isinstance(s, dict) and str(s.get("id") or "")
    }


def _set_generalizations(conns: object) -> Iterator[tuple[str, str, str]]:
    """Yield (conn_id, set_id, target) for each dt-generalization that names a set."""
    for conn in (conns if isinstance(conns, list) else []):
        if not isinstance(conn, dict) or str(conn.get("conn_type") or "") != "dt-generalization":
            continue
        set_id = str(conn.get("generalization_set") or "")
        if set_id:
            yield str(conn.get("id") or ""), set_id, str(conn.get("target") or "")


def _generalization_set_errors(fm: dict[str, Any]) -> list[str]:
    """Pure E339 logic: unknown set references and sets spanning differing general ends."""
    set_ids = _declared_set_ids(fm.get("diagram-entities"))
    targets_by_set: dict[str, set[str]] = {}
    errors: list[str] = []
    for conn_id, set_id, target in _set_generalizations(fm.get("connections")):
        if set_id not in set_ids:
            errors.append(
                f"dt-generalization '{conn_id}' references unknown generalization_set '{set_id}'"
            )
        else:
            targets_by_set.setdefault(set_id, set()).add(target)
    errors.extend(
        f"generalization_set '{set_id}' groups generalizations with differing "
        f"general ends: {sorted(targets)}"
        for set_id, targets in targets_by_set.items()
        if len(targets) > 1
    )
    return errors


class _GeneralizationSetContribution:
    """E339 — generalization_set references resolve and group a single general (target) end."""

    diagnostic_codes: tuple[str, ...] = ("E339",)

    def run(self, candidate: Any, ctx: BaseDiagramVerificationContext, result: Any) -> None:
        del candidate
        from src.domain.verification_findings import Issue, Severity  # noqa: PLC0415

        result.issues.extend(
            Issue(Severity.ERROR, "E339", message, ctx.loc)
            for message in _generalization_set_errors(ctx.fm)
        )


GENERALIZATION_SET_CONTRIBUTION = _GeneralizationSetContribution()

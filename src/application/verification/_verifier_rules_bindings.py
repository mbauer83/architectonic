"""Verifier rules for top-level diagram bindings.

E401: binding subject element not found in diagram.
E402: binding target entity_id unknown or out of scope.
E403: binding target connection_id unknown or out of scope.
E404: duplicate 'represents' binding for the same subject element.
E405: duplicate diagram-level 'scoped-by' binding.
E406: correspondence_kind not in the allowed set (core five + module-declared kinds for the element type).
E407: a member of target.connection_ids is unknown or out of scope.
E408: duplicate 'represents' binding for the same model target (without visual_roles).
E408b: occurrence visual_role missing, not in the declared set, or duplicated for the same target.
"""

from __future__ import annotations

from typing import Literal

from src.application.verification._verifier_rules_binding_targets import RepresentsTracker, check_binding_target
from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult
from src.domain.diagrams.allowed_bindings import AllowedBindingsSpec
from src.domain.diagrams.bindings import CORE_CORRESPONDENCE_KINDS
from src.domain.modules.catalogs import DiagramTypeCatalog


def get_allowed_bindings(
    diagram_type: str,
    diagram_type_catalog: DiagramTypeCatalog | None = None,
) -> AllowedBindingsSpec | None:
    """Return AllowedBindingsSpec for a diagram type, or None if unknown/not declared.

    When diagram_type_catalog is None the diagram type's extended bindings are not
    checked (falls back to core correspondence kinds only).
    """
    if not diagram_type or diagram_type_catalog is None:
        return None
    try:
        mod = diagram_type_catalog.find_diagram_type(diagram_type)
    except Exception:  # noqa: BLE001
        return None
    if mod is None:
        return None
    guidance = mod.write_guidance()
    ab = guidance.allowed_bindings
    return ab if ab is not None and not ab.is_empty() else None


# ---------------------------------------------------------------------------
# Public entry point — called from check_diagram_references_scoped (_verifier_rules_diagram_references)
# ---------------------------------------------------------------------------


def check_bindings_scoped(
    fm: dict,
    file_scope: Literal["enterprise", "engagement", "unknown"],
    allowed_entities: set[str],
    allowed_connections: set[str],
    all_entities: set[str],
    all_connections: set[str],
    result: VerificationResult,
    loc: str,
    allowed_bindings: AllowedBindingsSpec | None = None,
) -> None:
    """Validate top-level bindings in a diagram's frontmatter.

    Skips silently when there are no bindings.
    ``allowed_bindings`` is the diagram module's declared admissibility spec;
    when None the verifier falls back to the core five correspondence kinds.
    """
    raw_bindings = fm.get("bindings")
    if not raw_bindings or not isinstance(raw_bindings, list):
        return

    entity_element_ids = _collect_entity_element_ids(fm)
    connection_element_ids = _collect_connection_element_ids(fm)
    entity_type_map = _build_entity_type_map(fm)

    _check_bindings(
        raw_bindings,
        entity_element_ids,
        connection_element_ids,
        entity_type_map,
        file_scope,
        allowed_entities,
        allowed_connections,
        all_entities,
        all_connections,
        result,
        loc,
        allowed_bindings,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _collect_entity_element_ids(fm: dict) -> set[str]:
    ids: set[str] = set()
    de = fm.get("diagram-entities")
    if not isinstance(de, dict):
        return ids
    for items in de.values():
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("id") is not None:
                    ids.add(str(item["id"]))
    return ids


def _collect_connection_element_ids(fm: dict) -> set[str]:
    ids: set[str] = set()
    conns = fm.get("connections")
    if not isinstance(conns, list):
        return ids
    for item in conns:
        if isinstance(item, dict) and item.get("id") is not None:
            ids.add(str(item["id"]))
    return ids


def _build_entity_type_map(fm: dict) -> dict[str, str]:
    """Map entity element id → entity type from diagram-entities."""
    mapping: dict[str, str] = {}
    de = fm.get("diagram-entities")
    if not isinstance(de, dict):
        return mapping
    for etype, items in de.items():
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("id") is not None:
                    mapping[str(item["id"])] = str(etype)
    return mapping


def _allowed_kinds_for_entity(
    element_id: str,
    entity_type_map: dict[str, str],
    allowed_bindings: AllowedBindingsSpec | None,
) -> frozenset[str]:
    """Return allowed correspondence kinds for an entity subject."""
    if allowed_bindings is None:
        return CORE_CORRESPONDENCE_KINDS
    etype = entity_type_map.get(element_id)
    if etype is None:
        return CORE_CORRESPONDENCE_KINDS
    module_kinds = allowed_bindings.allowed_entity_kinds(etype)
    return module_kinds if module_kinds is not None else CORE_CORRESPONDENCE_KINDS


def _check_bindings(
    raw_bindings: list,
    entity_element_ids: set[str],
    connection_element_ids: set[str],
    entity_type_map: dict[str, str],
    file_scope: Literal["enterprise", "engagement", "unknown"],
    allowed_entities: set[str],
    allowed_connections: set[str],
    all_entities: set[str],
    all_connections: set[str],
    result: VerificationResult,
    loc: str,
    allowed_bindings: AllowedBindingsSpec | None,
) -> None:
    represents_by_subject: dict[str, str] = {}   # subject_id → first binding id
    represents_tracker = RepresentsTracker()
    scoped_by_diagram_count = 0

    for raw in raw_bindings:
        if not isinstance(raw, dict):
            continue

        binding_id = str(raw.get("id") or "(no-id)")
        subject = raw.get("subject")
        corr_kind = str(raw.get("correspondence_kind") or "")
        target = raw.get("target")

        # --- subject resolution ---
        if not isinstance(subject, dict):
            continue
        subject_kind = str(subject.get("kind") or "")
        subject_id = subject.get("id")

        # --- E406: correspondence_kind check ---
        _check_correspondence_kind(
            binding_id, corr_kind, subject_kind, subject_id,
            entity_type_map, allowed_bindings, result, loc,
        )

        if subject_kind == "diagram":
            _handle_diagram_subject(binding_id, subject_id, corr_kind, result, loc)
            if corr_kind == "scoped-by":
                scoped_by_diagram_count += 1
                if scoped_by_diagram_count > 1:
                    result.issues.append(
                        Issue(
                            Severity.ERROR, "E405",
                            f"binding '{binding_id}': diagram may have at most one diagram-level 'scoped-by' binding",
                            loc,
                        )
                    )
        elif subject_kind == "entity":
            subject_id_str = str(subject_id) if subject_id is not None else ""
            if not subject_id_str or subject_id_str not in entity_element_ids:
                result.issues.append(
                    Issue(
                        Severity.ERROR, "E401",
                        f"binding '{binding_id}': subject entity element "
                        f"'{subject_id_str}' not found in diagram-entities",
                        loc,
                    )
                )
            elif corr_kind == "represents":
                if subject_id_str in represents_by_subject:
                    result.issues.append(
                        Issue(
                            Severity.ERROR, "E404",
                            (
                                f"binding '{binding_id}': duplicate 'represents' binding for "
                                f"subject element '{subject_id_str}' "
                                f"(first seen in binding '{represents_by_subject[subject_id_str]}')"
                            ),
                            loc,
                        )
                    )
                else:
                    represents_by_subject[subject_id_str] = binding_id
        elif subject_kind == "connection":
            subject_id_str = str(subject_id) if subject_id is not None else ""
            if not subject_id_str or subject_id_str not in connection_element_ids:
                result.issues.append(
                    Issue(
                        Severity.ERROR, "E401",
                        f"binding '{binding_id}': subject connection element "
                        f"'{subject_id_str}' not found in diagram connections",
                        loc,
                    )
                )

        # --- target resolution ---
        if not isinstance(target, dict):
            continue

        # Register this target's declared visual_roles (for E408/E408b)
        if (
            subject_kind == "entity"
            and subject_id is not None
            and "entity_id" in target
            and target["entity_id"] is not None
        ):
            etype = entity_type_map.get(str(subject_id))
            if etype and allowed_bindings is not None:
                roles = allowed_bindings.visual_roles_for(etype)
                represents_tracker.roles_for_target[str(target["entity_id"])] = roles
            elif etype == "occurrence":
                represents_tracker.roles_for_target[str(target["entity_id"])] = ("*",)

        check_binding_target(
            binding_id, corr_kind, target,
            entity_element_ids, connection_element_ids,
            file_scope, allowed_entities, allowed_connections,
            all_entities, all_connections,
            represents_tracker,
            result, loc,
            visual_role=str(raw["visual_role"]) if raw.get("visual_role") is not None else None,
        )


def _check_correspondence_kind(
    binding_id: str,
    corr_kind: str,
    subject_kind: str,
    subject_id: object,
    entity_type_map: dict[str, str],
    allowed_bindings: AllowedBindingsSpec | None,
    result: VerificationResult,
    loc: str,
) -> None:
    if subject_kind == "entity" and subject_id is not None:
        valid_kinds = _allowed_kinds_for_entity(str(subject_id), entity_type_map, allowed_bindings)
    else:
        valid_kinds = CORE_CORRESPONDENCE_KINDS

    if corr_kind not in valid_kinds:
        result.issues.append(
            Issue(
                Severity.ERROR, "E406",
                (
                    f"binding '{binding_id}': correspondence_kind '{corr_kind}' "
                    f"is not allowed for this element "
                    f"(allowed: {', '.join(sorted(valid_kinds))})"
                ),
                loc,
            )
        )


def _handle_diagram_subject(
    binding_id: str,
    subject_id: object,
    corr_kind: str,
    result: VerificationResult,
    loc: str,
) -> None:
    if subject_id is not None:
        result.issues.append(
            Issue(
                Severity.ERROR, "E401",
                f"binding '{binding_id}': diagram-level binding must have no subject.id (got '{subject_id}')",
                loc,
            )
        )

"""Verifier rules for datatype diagram bidirectional consistency (§3.2).

E330: a dt-* edge between two DOB-bound classifiers has no connection binding
      to a backing model connection (forward / missing-backing error).
E331: a connection binding exists but the backing connection's relationship_kind,
      endpoints, or direction do not correspond to the dt-* edge (reverse /
      non-corresponding-backing error).

No dt-*→archimate-* constant is present here.  Correspondence is derived
entirely from ConnectionTypeInfo.relationship_kind and .symmetric.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult
from src.application.verification.datatype_consistency import admissible_backing_kinds, corresponds
from src.domain.artifact_id import stable_conn_id
from src.domain.modules.catalogs import DiagramTypeCatalog, OntologyCatalog
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo

_DATATYPE = "datatype"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def check_datatype_backing_consistency(
    fm: dict,
    allowed_connections: set[str],
    ontology: OntologyCatalog,
    diagram_catalog: DiagramTypeCatalog | None,
    result: VerificationResult,
    loc: str,
) -> None:
    """Check §3.2 bidirectional consistency for datatype diagrams.

    Skips silently when diagram-type is not 'datatype'.
    """
    if str(fm.get("diagram-type", "")) != _DATATYPE:
        return

    entity_to_dob = _build_entity_dob_map(fm)
    if not entity_to_dob:
        return

    conn_to_model = _build_connection_model_map(fm)
    dt_types = _get_dt_connection_types(diagram_catalog)
    all_conn_types = ontology.all_connection_types()

    _raw_conns = fm.get("connections")
    if not isinstance(_raw_conns, list):
        return

    for conn in _raw_conns:
        if not isinstance(conn, dict):
            continue
        _check_one_connection(
            conn, entity_to_dob, conn_to_model, dt_types,
            allowed_connections, all_conn_types, result, loc,
        )


# ---------------------------------------------------------------------------
# Per-connection check
# ---------------------------------------------------------------------------


def _check_one_connection(
    conn: dict,
    entity_to_dob: dict[str, str],
    conn_to_model: dict[str, str],
    dt_types: dict[str, ConnectionTypeInfo],
    allowed_connections: set[str],
    all_conn_types: Mapping[str, ConnectionTypeInfo],
    result: VerificationResult,
    loc: str,
) -> None:
    conn_elem_id = str(conn.get("id") or "")
    conn_type = str(conn.get("conn_type") or "")
    source_elem = str(conn.get("source") or "")
    target_elem = str(conn.get("target") or "")

    if not conn_type.startswith("dt-"):
        return

    dob_source = entity_to_dob.get(source_elem)
    dob_target = entity_to_dob.get(target_elem)
    if dob_source is None or dob_target is None:
        return  # Rule only fires when both ends are DOB-bound (§10.6)

    dt_info = dt_types.get(conn_type)
    if dt_info is None:
        return  # Unknown dt-* type; schema checks handle it

    model_conn_id = conn_to_model.get(conn_elem_id)

    if model_conn_id is None:
        _emit_forward_error(
            conn_elem_id, conn_type, dt_info,
            dob_source, dob_target, all_conn_types, result, loc,
        )
    else:
        _emit_reverse_error_if_inconsistent(
            conn_elem_id, conn_type, dt_info,
            dob_source, dob_target, model_conn_id,
            allowed_connections, all_conn_types, result, loc,
        )


# ---------------------------------------------------------------------------
# Forward error (E330) — missing backing connection
# ---------------------------------------------------------------------------


def _emit_forward_error(
    conn_elem_id: str,
    conn_type: str,
    dt_info: ConnectionTypeInfo,
    dob_source: str,
    dob_target: str,
    all_conn_types: Mapping[str, ConnectionTypeInfo],
    result: VerificationResult,
    loc: str,
) -> None:
    permitted = sorted(admissible_backing_kinds(dt_info))
    preferred = _preferred_archimate_type(dt_info.relationship_kind, all_conn_types)
    result.issues.append(
        Issue(
            Severity.ERROR,
            "E330",
            (
                f"dt-* edge '{conn_elem_id}' ({conn_type}) between DOB-bound classifiers "
                f"has no connection binding to a backing model connection — "
                "create and bind an appropriate connection between the two Data Objects."
            ),
            loc,
            details={
                "dob_source": dob_source,
                "dob_target": dob_target,
                "dt_conn_id": conn_elem_id,
                "dt_relationship_kind": dt_info.relationship_kind,
                "permitted_backing_kinds": permitted,
                "preferred_default": preferred,
            },
            actions=(
                {
                    "type": "create_connection",
                    "connection_type": preferred,
                    "source": dob_source,
                    "target": dob_target,
                },
            ) if preferred else None,
        )
    )


# ---------------------------------------------------------------------------
# Reverse error (E331) — bound but non-corresponding backing
# ---------------------------------------------------------------------------


def _emit_reverse_error_if_inconsistent(
    conn_elem_id: str,
    conn_type: str,
    dt_info: ConnectionTypeInfo,
    dob_source: str,
    dob_target: str,
    model_conn_id: str,
    allowed_connections: set[str],
    all_conn_types: Mapping[str, ConnectionTypeInfo],
    result: VerificationResult,
    loc: str,
) -> None:
    allowed_short_conns = {stable_conn_id(c) for c in allowed_connections}
    if stable_conn_id(model_conn_id) not in allowed_short_conns:
        return  # E402/E403 handle unknown/out-of-scope targets

    parsed = _parse_model_conn_id(model_conn_id)
    if parsed is None:
        result.issues.append(
            Issue(
                Severity.ERROR, "E331",
                f"binding for edge '{conn_elem_id}': cannot parse model connection "
                f"id '{model_conn_id}' (expected src---tgt@@type format)",
                loc,
            )
        )
        return

    backing_src, backing_tgt, backing_type_name = parsed

    endpoints_match = (
        (backing_src == dob_source and backing_tgt == dob_target)
        or (backing_src == dob_target and backing_tgt == dob_source)
    )
    if not endpoints_match:
        result.issues.append(
            Issue(
                Severity.ERROR, "E331",
                (
                    f"dt-* edge '{conn_elem_id}' ({conn_type}) binds to "
                    f"'{model_conn_id}' whose endpoints ({backing_src}, {backing_tgt}) "
                    f"do not match the bound Data Objects ({dob_source}, {dob_target})"
                ),
                loc,
                details={
                    "dob_source": dob_source,
                    "dob_target": dob_target,
                    "dt_relationship_kind": dt_info.relationship_kind,
                    "backing_connection_id": model_conn_id,
                    "permitted_backing_kinds": sorted(admissible_backing_kinds(dt_info)),
                },
            )
        )
        return

    backing_info = all_conn_types.get(backing_type_name)
    if backing_info is None:
        return  # Unknown backing type; other rules handle

    same_direction = backing_src == dob_source
    if not corresponds(dt_info, backing_info, same_direction):
        result.issues.append(
            Issue(
                Severity.ERROR, "E331",
                (
                    f"dt-* edge '{conn_elem_id}' ({conn_type}, kind "
                    f"'{dt_info.relationship_kind}') does not correspond to backing "
                    f"connection '{model_conn_id}' ({backing_type_name}, kind "
                    f"'{backing_info.relationship_kind}')"
                ),
                loc,
                details={
                    "dob_source": dob_source,
                    "dob_target": dob_target,
                    "dt_relationship_kind": dt_info.relationship_kind,
                    "backing_connection_id": model_conn_id,
                    "backing_relationship_kind": backing_info.relationship_kind,
                    "permitted_backing_kinds": sorted(admissible_backing_kinds(dt_info)),
                },
            )
        )


# ---------------------------------------------------------------------------
# Helpers — parse bindings from frontmatter
# ---------------------------------------------------------------------------


def _build_entity_dob_map(fm: dict) -> dict[str, str]:
    """Map classifier element id → bound DOB entity id (from entity bindings)."""
    classifier_ids = _collect_classifier_ids(fm)
    result: dict[str, str] = {}
    for binding in _iter_bindings(fm):
        subject = binding.get("subject")
        if not isinstance(subject, dict) or str(subject.get("kind") or "") != "entity":
            continue
        subject_id = str(subject.get("id") or "")
        if not subject_id or subject_id not in classifier_ids:
            continue
        target = binding.get("target")
        if not isinstance(target, dict):
            continue
        entity_id = target.get("entity_id")
        if entity_id:
            result[subject_id] = str(entity_id)
    return result


def _build_connection_model_map(fm: dict) -> dict[str, str]:
    """Map diagram connection element id → bound model connection id."""
    result: dict[str, str] = {}
    for binding in _iter_bindings(fm):
        subject = binding.get("subject")
        if not isinstance(subject, dict) or str(subject.get("kind") or "") != "connection":
            continue
        subject_id = str(subject.get("id") or "")
        if not subject_id:
            continue
        target = binding.get("target")
        if not isinstance(target, dict):
            continue
        connection_id = target.get("connection_id")
        if connection_id:
            result[subject_id] = str(connection_id)
    return result


def _collect_classifier_ids(fm: dict) -> set[str]:
    ids: set[str] = set()
    de = fm.get("diagram-entities")
    if not isinstance(de, dict):
        return ids
    items = de.get("classifier")
    if not isinstance(items, list):
        return ids
    for item in items:
        if isinstance(item, dict) and item.get("id"):
            ids.add(str(item["id"]))
    return ids


def _iter_bindings(fm: dict):
    bindings = fm.get("bindings")
    if not isinstance(bindings, list):
        return
    for b in bindings:
        if isinstance(b, dict):
            yield b


# ---------------------------------------------------------------------------
# Helpers — ontology lookups
# ---------------------------------------------------------------------------


def _get_dt_connection_types(
    diagram_catalog: DiagramTypeCatalog | None,
) -> dict[str, ConnectionTypeInfo]:
    if diagram_catalog is None:
        return {}
    try:
        mod = diagram_catalog.find_diagram_type(_DATATYPE)
    except Exception:  # noqa: BLE001
        return {}
    if mod is None:
        return {}
    return {str(k): v for k, v in mod.own_connection_types.items()}


def _preferred_archimate_type(
    kind: str | None,
    all_conn_types: Mapping[str, ConnectionTypeInfo],
) -> str | None:
    """Return the first archimate connection type (alphabetically) with matching kind."""
    if not kind:
        return None
    matches = [
        name for name, info in all_conn_types.items()
        if info.relationship_kind == kind and info.conn_lang == "archimate"
    ]
    return min(matches) if matches else None


def _parse_model_conn_id(conn_id: str) -> tuple[str, str, str] | None:
    """Parse (src, tgt, type_name) from a canonical {src}---{tgt}@@{type} id."""
    dash = conn_id.find("---")
    if dash < 0:
        return None
    source = conn_id[:dash]
    rest = conn_id[dash + 3:]
    at = rest.find("@@")
    if at < 0:
        return None
    target = rest[:at]
    type_name = rest[at + 2:]
    return source, target, type_name

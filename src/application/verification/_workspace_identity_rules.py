"""WU-0.6: E335 — generic workspace-id uniqueness check.

Registered into _GENERIC_REPOSITORY_CONTRIBUTIONS on import.
"""

from __future__ import annotations

import re
from typing import Any


def _collect_workspace_types(catalogs: Any) -> list[str]:
    """Return all entity-type names with identity_scope=='workspace' across all diagram modules."""
    ws: list[str] = []
    try:
        for mod in catalogs.diagram_types.all_diagram_types().values():
            for ui_cfg in mod.ui_config.diagram_only_types:
                if ui_cfg.identity_scope == "workspace":
                    ws.append(ui_cfg.entity_type)
    except Exception:  # noqa: BLE001
        pass
    return ws


class WorkspaceIdUniquenessContribution:
    """E335: detects workspace-id cross-diagram conflicts in the candidate transaction."""

    diagnostic_codes: tuple[str, ...] = ("E335",)

    def run(self, ctx: Any, result: Any) -> None:
        if ctx.catalogs is None:
            return
        from src.application.verification.artifact_verifier_types import Issue, Severity  # noqa: PLC0415

        ws_types = _collect_workspace_types(ctx.catalogs)
        if not ws_types:
            return

        # For each workspace entity in the candidate, compare its host_diagram_id
        # against the committed view.  A mismatch means the id is claimed by a
        # different diagram → E335.
        seen_conflicts: set[str] = set()
        severity = Severity.ERROR if ctx.type_references_blocking else Severity.WARNING
        for ws_type in ws_types:
            for cand_e in ctx.candidate.list_entities(artifact_type=ws_type):
                aid = cand_e.artifact_id
                if aid in seen_conflicts:
                    continue
                comm_e = ctx.committed.get_entity(aid)
                if comm_e is None:
                    continue
                if comm_e.host_diagram_id == cand_e.host_diagram_id:
                    continue
                seen_conflicts.add(aid)
                result.issues.append(Issue(
                    severity,
                    "E335",
                    (
                        f"Workspace entity '{aid}' is claimed by diagram "
                        f"'{cand_e.host_diagram_id}' but already owned by "
                        f"'{comm_e.host_diagram_id}'"
                    ),
                    ctx.location,
                    details={
                        "artifact_id": aid,
                        "candidate_host": cand_e.host_diagram_id,
                        "committed_host": comm_e.host_diagram_id,
                    },
                ))


# ---------------------------------------------------------------------------
# Workspace-id format helpers (used by the write-path format check)
# ---------------------------------------------------------------------------

_WORKSPACE_ID_RE = re.compile(r"^[A-Z]+@[0-9]+\.[A-Za-z0-9_-]+\..+$")


def validate_workspace_entity_ids(
    diagram_entities: dict | None,
    module: Any,
    *,
    committed_ids: set[str] | None = None,
) -> list[str]:
    """Return error messages for workspace entity ids that violate the prefix grammar.

    Validates ONLY new ids (not already in *committed_ids*).  When creating a
    diagram all ids are new so pass ``committed_ids=None`` (equivalent to empty set).
    """
    if not isinstance(diagram_entities, dict):
        return []
    committed = committed_ids or set()
    errors: list[str] = []

    try:
        own_types = module.ui_config.diagram_only_types
    except Exception:  # noqa: BLE001
        return []

    for ui_cfg in own_types:
        if ui_cfg.identity_scope != "workspace" or ui_cfg.id_prefix is None:
            continue
        prefix = ui_cfg.id_prefix
        et_name = str(ui_cfg.entity_type)
        prefix_re = re.compile(
            rf"^{re.escape(prefix)}@[0-9]+\.[A-Za-z0-9_-]+\..+$"
        )
        items: list[Any] = diagram_entities.get(et_name) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            eid = str(item.get("id") or "")
            if not eid or eid in committed:
                continue
            if not prefix_re.match(eid):
                errors.append(
                    f"Workspace entity id '{eid}' for type '{et_name}' must match "
                    f"'{prefix}@EPOCH.RANDOM.SLUG'"
                )
    return errors


# ---------------------------------------------------------------------------
# Register E335 into the central generic registry (idempotent, import-time)
# ---------------------------------------------------------------------------
from src.domain.diagrams.diagram_verification import _GENERIC_REPOSITORY_CONTRIBUTIONS  # noqa: E402

_E335_SINGLETON = WorkspaceIdUniquenessContribution()
if not any(isinstance(c, WorkspaceIdUniquenessContribution) for c in _GENERIC_REPOSITORY_CONTRIBUTIONS):
    _GENERIC_REPOSITORY_CONTRIBUTIONS.append(_E335_SINGLETON)

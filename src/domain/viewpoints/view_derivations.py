"""ViewDerivation data model — diagram-level derivation specifications.

Each view_derivations entry records how a derived view was produced:
which strategy was run, at which version, against which model scope,
with which parameters and user inclusion/exclusion decisions.

Serialisation: top-level ``view_derivations:`` frontmatter key on diagrams.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

VALID_REPO_SCOPES: frozenset[str] = frozenset({"enterprise", "engagement", "both"})


@dataclass(frozen=True)
class SourceModelSnapshot:
    repo_scope: str
    root_entity_id: str | None = None
    root_entity_ids: tuple[str, ...] | None = None


@dataclass(frozen=True)
class PathProvenance:
    """What a witness path was accepted (or reviewed) as, at generation/acceptance
    time — the baseline refresh compares a fresh reconstruction against to detect
    certainty/type drift, distinct from an outright-broken or no-longer-derives path."""

    certainty: str  # "certain" | "potential"
    connection_type: str


@dataclass(frozen=True)
class DerivationSelection:
    included_entity_ids: tuple[str, ...] = ()
    excluded_entity_ids: tuple[str, ...] = ()
    included_connection_ids: tuple[str, ...] = ()
    excluded_connection_ids: tuple[str, ...] = ()
    included_paths: tuple[str, ...] = ()  # canonical path keys: id1@fwd|id2@rev|...
    excluded_paths: tuple[str, ...] = ()
    path_provenance: Mapping[str, PathProvenance] = field(default_factory=dict)  # path key -> accepted-as record


@dataclass(frozen=True)
class ViewDerivation:
    id: str
    strategy: str
    strategy_version: int
    source_model_snapshot: SourceModelSnapshot
    parameters: dict[str, object] = field(default_factory=dict)
    selection: DerivationSelection | None = None
    generated_at: str | None = None


# ---------------------------------------------------------------------------
# JSON Schema
# ---------------------------------------------------------------------------

VIEW_DERIVATIONS_SCHEMA: dict[str, object] = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["id", "strategy", "strategy_version", "source_model_snapshot"],
        "properties": {
            "id": {"type": "string"},
            "strategy": {"type": "string"},
            "strategy_version": {"type": "integer"},
            "source_model_snapshot": {
                "type": "object",
                "required": ["repo_scope"],
                "properties": {
                    "repo_scope": {"type": "string", "enum": list(VALID_REPO_SCOPES)},
                    "root_entity_id": {"type": "string"},
                    "root_entity_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
            "parameters": {"type": "object"},
            "selection": {
                "type": "object",
                "properties": {
                    "included_entity_ids": {"type": "array", "items": {"type": "string"}},
                    "excluded_entity_ids": {"type": "array", "items": {"type": "string"}},
                    "included_connection_ids": {"type": "array", "items": {"type": "string"}},
                    "excluded_connection_ids": {"type": "array", "items": {"type": "string"}},
                    "included_paths": {"type": "array", "items": {"type": "string"}},
                    "excluded_paths": {"type": "array", "items": {"type": "string"}},
                    "path_provenance": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "object",
                            "required": ["certainty", "connection_type"],
                            "properties": {
                                "certainty": {"type": "string", "enum": ["certain", "potential"]},
                                "connection_type": {"type": "string"},
                            },
                        },
                    },
                },
            },
            "generated_at": {"type": "string"},
        },
    },
}

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_source_model_snapshot(raw: dict[str, object]) -> SourceModelSnapshot:
    repo_scope = str(raw.get("repo_scope", ""))
    root_entity_id = str(raw["root_entity_id"]) if raw.get("root_entity_id") is not None else None
    raw_ids = raw.get("root_entity_ids")
    root_entity_ids = tuple(str(x) for x in raw_ids) if isinstance(raw_ids, list) else None
    return SourceModelSnapshot(
        repo_scope=repo_scope,
        root_entity_id=root_entity_id,
        root_entity_ids=root_entity_ids,
    )


def _parse_path_provenance(raw: object) -> dict[str, PathProvenance]:
    if not isinstance(raw, dict):
        return {}
    provenance: dict[str, PathProvenance] = {}
    for path_key, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        certainty = entry.get("certainty")
        connection_type = entry.get("connection_type")
        if isinstance(certainty, str) and isinstance(connection_type, str):
            provenance[str(path_key)] = PathProvenance(certainty=certainty, connection_type=connection_type)
    return provenance


def _parse_selection(raw: dict[str, object]) -> DerivationSelection:
    def _ids(key: str) -> tuple[str, ...]:
        v = raw.get(key)
        return tuple(str(x) for x in v) if isinstance(v, list) else ()

    return DerivationSelection(
        included_entity_ids=_ids("included_entity_ids"),
        excluded_entity_ids=_ids("excluded_entity_ids"),
        included_connection_ids=_ids("included_connection_ids"),
        excluded_connection_ids=_ids("excluded_connection_ids"),
        included_paths=_ids("included_paths"),
        excluded_paths=_ids("excluded_paths"),
        path_provenance=_parse_path_provenance(raw.get("path_provenance")),
    )


def parse_view_derivation(raw: dict[str, object]) -> ViewDerivation:
    snapshot_raw = raw.get("source_model_snapshot")
    if not isinstance(snapshot_raw, dict):
        raise ValueError(
            f"view_derivation '{raw.get('id')}': source_model_snapshot must be a dict"
        )
    snapshot = _parse_source_model_snapshot(snapshot_raw)

    parameters = raw.get("parameters")
    if not isinstance(parameters, dict):
        parameters = {}

    selection_raw = raw.get("selection")
    selection = _parse_selection(selection_raw) if isinstance(selection_raw, dict) else None

    sv = raw.get("strategy_version")
    strategy_version = int(sv) if isinstance(sv, (int, float)) else 0

    return ViewDerivation(
        id=str(raw.get("id", "")),
        strategy=str(raw.get("strategy", "")),
        strategy_version=strategy_version,
        source_model_snapshot=snapshot,
        parameters=dict(parameters),
        selection=selection,
        generated_at=str(raw["generated_at"]) if raw.get("generated_at") is not None else None,
    )


def parse_view_derivations(raw: list[object] | None) -> list[ViewDerivation]:
    if not raw:
        return []
    return [parse_view_derivation(item) for item in raw if isinstance(item, dict)]


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _selection_to_dict(sel: DerivationSelection) -> dict[str, object]:
    result: dict[str, object] = {}
    if sel.included_entity_ids:
        result["included_entity_ids"] = list(sel.included_entity_ids)
    if sel.excluded_entity_ids:
        result["excluded_entity_ids"] = list(sel.excluded_entity_ids)
    if sel.included_connection_ids:
        result["included_connection_ids"] = list(sel.included_connection_ids)
    if sel.excluded_connection_ids:
        result["excluded_connection_ids"] = list(sel.excluded_connection_ids)
    if sel.included_paths:
        result["included_paths"] = list(sel.included_paths)
    if sel.excluded_paths:
        result["excluded_paths"] = list(sel.excluded_paths)
    if sel.path_provenance:
        result["path_provenance"] = {
            path_key: {"certainty": entry.certainty, "connection_type": entry.connection_type}
            for path_key, entry in sel.path_provenance.items()
        }
    return result


def _snapshot_to_dict(snap: SourceModelSnapshot) -> dict[str, object]:
    result: dict[str, object] = {"repo_scope": snap.repo_scope}
    if snap.root_entity_id is not None:
        result["root_entity_id"] = snap.root_entity_id
    if snap.root_entity_ids is not None:
        result["root_entity_ids"] = list(snap.root_entity_ids)
    return result


def view_derivation_to_dict(vd: ViewDerivation) -> dict[str, object]:
    result: dict[str, object] = {
        "id": vd.id,
        "strategy": vd.strategy,
        "strategy_version": vd.strategy_version,
        "source_model_snapshot": _snapshot_to_dict(vd.source_model_snapshot),
    }
    if vd.parameters:
        result["parameters"] = vd.parameters
    if vd.selection is not None:
        sel_dict = _selection_to_dict(vd.selection)
        if sel_dict:
            result["selection"] = sel_dict
    if vd.generated_at is not None:
        result["generated_at"] = vd.generated_at
    return result


def view_derivations_to_raw(vds: list[ViewDerivation]) -> list[dict[str, object]]:
    return [view_derivation_to_dict(vd) for vd in vds]

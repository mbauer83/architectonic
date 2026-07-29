"""Derivation refresh: revision hashing, diff computation, selection delta application.

``compute_revision`` hashes a diagram file so callers can detect concurrent edits
(``base_revision`` in the stateless stale-write contract).

``compute_derivation_diff`` runs a registered strategy against the current model and
computes the delta vs the stored selection, returning a ``DerivationDiff`` the caller
can echo back to apply-diff (trimmed or in full).

``apply_selection_delta`` applies a ``SelectionDelta`` to the raw view_derivations
YAML list and returns the updated list.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from src.application.derivation.path_staleness import classify_accepted_path_staleness
from src.application.derivation.strategy_registry import DerivationStrategyCatalog
from src.application.derivation.types import ModelQuery
from src.domain.modules.module_catalog import ModuleCatalog
from src.domain.viewpoints.view_derivations import ViewDerivation


def compute_revision(path: Path) -> str:
    """Return a 16-hex-char SHA-256 hash of the file content."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Path key helpers
# ---------------------------------------------------------------------------


def _parse_path_key(path_key: str) -> list[tuple[str, bool]]:
    """Parse 'id1@fwd|id2@rev|...' into [(conn_id, reversed), ...]."""
    steps = []
    for part in path_key.split("|"):
        if "@" in part:
            conn_id, orient = part.rsplit("@", 1)
            steps.append((conn_id, orient == "rev"))
        elif part:
            steps.append((part, False))
    return steps


def _is_path_well_formed(path_key: str, known_connection_ids: set[str]) -> bool:
    """Return True if every step id in the path key exists in known_connection_ids."""
    for conn_id, _ in _parse_path_key(path_key):
        if conn_id not in known_connection_ids:
            return False
    return True


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class SelectionDelta:
    """Proposed changes to one view_derivation's selection."""

    add_included_entity_ids: list[str] = field(default_factory=list)
    add_excluded_entity_ids: list[str] = field(default_factory=list)
    add_included_connection_ids: list[str] = field(default_factory=list)
    add_excluded_connection_ids: list[str] = field(default_factory=list)
    remove_included_entity_ids: list[str] = field(default_factory=list)
    remove_included_connection_ids: list[str] = field(default_factory=list)
    add_included_paths: list[str] = field(default_factory=list)
    add_excluded_paths: list[str] = field(default_factory=list)
    remove_included_paths: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any([
            self.add_included_entity_ids, self.add_excluded_entity_ids,
            self.add_included_connection_ids, self.add_excluded_connection_ids,
            self.remove_included_entity_ids, self.remove_included_connection_ids,
            self.add_included_paths, self.add_excluded_paths, self.remove_included_paths,
        ])

    def to_dict(self) -> dict[str, object]:
        return {
            "add_included_entity_ids": self.add_included_entity_ids,
            "add_excluded_entity_ids": self.add_excluded_entity_ids,
            "add_included_connection_ids": self.add_included_connection_ids,
            "add_excluded_connection_ids": self.add_excluded_connection_ids,
            "remove_included_entity_ids": self.remove_included_entity_ids,
            "remove_included_connection_ids": self.remove_included_connection_ids,
            "add_included_paths": self.add_included_paths,
            "add_excluded_paths": self.add_excluded_paths,
            "remove_included_paths": self.remove_included_paths,
        }


@dataclass
class DerivationDiff:
    """Self-contained diff for one view_derivations entry.

    Returned by refresh-derivation; echoed back (optionally trimmed) in apply-diff.
    path_* fields are only populated when the strategy outputs paths (path-projection).
    """

    base_revision: str
    diff_id: str
    derivation_id: str
    new_entity_ids: list[str]
    new_connection_ids: list[str]
    gone_entity_ids: list[str]
    gone_connection_ids: list[str]
    selection_delta: SelectionDelta
    remove_binding_ids: list[str]
    new_paths: list[str] = field(default_factory=list)
    gone_paths: list[str] = field(default_factory=list)
    drifted_paths: list[str] = field(default_factory=list)
    broken_paths: list[str] = field(default_factory=list)
    no_longer_derives_paths: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (
            self.new_entity_ids or self.new_connection_ids
            or self.gone_entity_ids or self.gone_connection_ids
            or self.new_paths or self.gone_paths
        )

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "base_revision": self.base_revision,
            "diff_id": self.diff_id,
            "derivation_id": self.derivation_id,
            "new_entity_ids": self.new_entity_ids,
            "new_connection_ids": self.new_connection_ids,
            "gone_entity_ids": self.gone_entity_ids,
            "gone_connection_ids": self.gone_connection_ids,
            "selection_delta": self.selection_delta.to_dict(),
            "remove_binding_ids": self.remove_binding_ids,
            "is_empty": self.is_empty,
        }
        if self.new_paths or self.drifted_paths or self.broken_paths or self.gone_paths:
            result["new_paths"] = self.new_paths
            result["gone_paths"] = self.gone_paths
            result["drifted_paths"] = self.drifted_paths
            result["broken_paths"] = self.broken_paths
            result["no_longer_derives_paths"] = self.no_longer_derives_paths
        return result


# ---------------------------------------------------------------------------
# Core diff computation
# ---------------------------------------------------------------------------


def compute_derivation_diff(
    diagram_path: Path,
    fm: dict[str, object],
    vd: ViewDerivation,
    query: ModelQuery,
    catalog: DerivationStrategyCatalog | None = None,
    *,
    ontology_catalog: ModuleCatalog | None = None,
) -> DerivationDiff:
    """Run the strategy and compute the diff vs the stored selection.

    Raises ValueError if no derive function is found for the strategy.
    Manual-beats-refresh: only bindings with derived_from == vd.id targeting gone
    entities are proposed for removal; manual bindings are never touched.

    ``ontology_catalog``, when supplied, switches accepted-path staleness from the
    shallow connection-existence check to full reconstruction (broken /
    no-longer-derives / certainty-or-type drift) via ``classify_accepted_path_staleness``
    — the only way to see drift at all, since a path key names which connections form a
    chain, never what it currently resolves to.
    """
    base_revision = compute_revision(diagram_path)

    derive_fn = catalog.lookup_derive_fn(vd.strategy, vd.strategy_version) if catalog else None
    if derive_fn is None:
        raise ValueError(
            f"No derive function registered for strategy '{vd.strategy}' v{vd.strategy_version}."
        )

    candidate_set = derive_fn(vd.parameters, vd.source_model_snapshot, query)

    sel = vd.selection
    inc_entities: set[str] = set(sel.included_entity_ids) if sel else set()
    exc_entities: set[str] = set(sel.excluded_entity_ids) if sel else set()
    inc_connections: set[str] = set(sel.included_connection_ids) if sel else set()
    exc_connections: set[str] = set(sel.excluded_connection_ids) if sel else set()
    inc_paths: set[str] = set(sel.included_paths) if sel else set()
    exc_paths: set[str] = set(sel.excluded_paths) if sel else set()

    new_entity_ids = sorted(
        eid for eid in candidate_set.entity_ids
        if eid not in inc_entities and eid not in exc_entities
    )
    new_connection_ids = sorted(
        cid for cid in candidate_set.connection_ids
        if cid not in inc_connections and cid not in exc_connections
    )
    gone_entity_ids = sorted(eid for eid in inc_entities if eid not in candidate_set.entity_ids)
    gone_connection_ids = sorted(cid for cid in inc_connections if cid not in candidate_set.connection_ids)

    # Path diff: new candidates are a plain set difference; staleness of already-accepted
    # paths uses full reconstruction when an ontology catalog is available (the only way
    # to see certainty/type drift), else falls back to the shallow well-formedness check.
    new_paths = sorted(pk for pk in candidate_set.paths if pk not in inc_paths and pk not in exc_paths)
    if ontology_catalog is not None:
        staleness = classify_accepted_path_staleness(sel, read_access=query, catalog=ontology_catalog)
        broken_paths = list(staleness.broken_paths)
        no_longer_derives_paths = list(staleness.no_longer_derives_paths)
        drifted_paths = list(staleness.drifted_paths)
        gone_paths = sorted(staleness.stale_paths)
    else:
        known_conn_ids = query.connection_ids()
        gone_path_keys = [pk for pk in inc_paths if pk not in candidate_set.paths]
        drifted_paths = sorted(pk for pk in gone_path_keys if _is_path_well_formed(pk, known_conn_ids))
        broken_paths = sorted(pk for pk in gone_path_keys if not _is_path_well_formed(pk, known_conn_ids))
        no_longer_derives_paths = []
        gone_paths = sorted(gone_path_keys)

    delta = SelectionDelta(
        add_included_entity_ids=new_entity_ids,
        add_included_connection_ids=new_connection_ids,
        remove_included_entity_ids=gone_entity_ids,
        remove_included_connection_ids=gone_connection_ids,
        add_included_paths=new_paths,
        remove_included_paths=gone_paths,
    )

    # Bindings to propose for removal: derived bindings targeting gone entities or gone paths
    gone_entity_set = set(gone_entity_ids)
    gone_path_set = set(gone_paths)
    _raw_bindings = fm.get("bindings")
    _bindings_list = _raw_bindings if isinstance(_raw_bindings, list) else []
    remove_binding_ids = []
    for b in _bindings_list:
        if not isinstance(b, dict):
            continue
        if str(b.get("derived_from") or "") != vd.id:
            continue
        tgt: object = b.get("target") or {}
        if isinstance(tgt, dict):
            if str(tgt.get("entity_id", "")) in gone_entity_set:
                remove_binding_ids.append(str(b.get("id")))
            elif tgt.get("connection_path") is not None:
                # Re-build path key from stored connection_path to check against gone set
                cp = tgt["connection_path"]
                if isinstance(cp, list):
                    parts = [
                        f"{s['id']}@{'rev' if s.get('reversed') else 'fwd'}"
                        for s in cp if isinstance(s, dict) and s.get("id")
                    ]
                    pk = "|".join(parts)
                    if pk in gone_path_set:
                        remove_binding_ids.append(str(b.get("id")))

    diff_body = f"{base_revision}:{vd.id}:{new_entity_ids}:{new_connection_ids}:{gone_entity_ids}:{new_paths}"
    diff_id = hashlib.sha256(diff_body.encode()).hexdigest()[:12]

    return DerivationDiff(
        base_revision=base_revision,
        diff_id=diff_id,
        derivation_id=vd.id,
        new_entity_ids=new_entity_ids,
        new_connection_ids=new_connection_ids,
        gone_entity_ids=gone_entity_ids,
        gone_connection_ids=gone_connection_ids,
        selection_delta=delta,
        remove_binding_ids=remove_binding_ids,
        new_paths=new_paths,
        gone_paths=gone_paths,
        drifted_paths=drifted_paths,
        broken_paths=broken_paths,
        no_longer_derives_paths=no_longer_derives_paths,
    )


# ---------------------------------------------------------------------------
# Selection delta application
# ---------------------------------------------------------------------------


def apply_selection_delta(
    raw_view_derivations: list[dict[str, object]],
    derivation_id: str,
    delta: SelectionDelta,
) -> list[dict[str, object]]:
    """Return a new raw view_derivations list with the delta applied to the named entry."""
    result: list[dict[str, object]] = []
    for raw_vd in raw_view_derivations:
        if not isinstance(raw_vd, dict) or str(raw_vd.get("id")) != derivation_id:
            result.append(raw_vd)
            continue

        raw_sel = raw_vd.get("selection")
        existing = raw_sel if isinstance(raw_sel, dict) else {}

        inc_ents = (set(existing.get("included_entity_ids") or [])
                    | set(delta.add_included_entity_ids)
                    ) - set(delta.remove_included_entity_ids)
        exc_ents = set(existing.get("excluded_entity_ids") or []) | set(delta.add_excluded_entity_ids)
        inc_conns = (set(existing.get("included_connection_ids") or [])
                     | set(delta.add_included_connection_ids)
                     ) - set(delta.remove_included_connection_ids)
        exc_conns = set(existing.get("excluded_connection_ids") or []) | set(delta.add_excluded_connection_ids)
        inc_paths = (set(existing.get("included_paths") or [])
                     | set(delta.add_included_paths)
                     ) - set(delta.remove_included_paths)
        exc_paths = set(existing.get("excluded_paths") or []) | set(delta.add_excluded_paths)

        new_sel: dict[str, object] = {}
        if inc_ents:
            new_sel["included_entity_ids"] = sorted(inc_ents)
        if exc_ents:
            new_sel["excluded_entity_ids"] = sorted(exc_ents)
        if inc_conns:
            new_sel["included_connection_ids"] = sorted(inc_conns)
        if exc_conns:
            new_sel["excluded_connection_ids"] = sorted(exc_conns)
        if inc_paths:
            new_sel["included_paths"] = sorted(inc_paths)
        if exc_paths:
            new_sel["excluded_paths"] = sorted(exc_paths)

        new_vd = dict(raw_vd)
        if new_sel:
            new_vd["selection"] = new_sel
        else:
            new_vd.pop("selection", None)
        result.append(new_vd)
    return result

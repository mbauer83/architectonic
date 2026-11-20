"""Generate markdown matrix tables from entity IDs and connection-type configs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.domain.markdown_table import escape_cell, format_table


@dataclass
class ConnTypeConfig:
    conn_type: str
    active: bool = True


def build_matrix_tables(
    *,
    entity_ids: list[str],
    conn_type_configs: list[ConnTypeConfig],
    combined: bool = False,
    entity_names: dict[str, str],
    connections: list[Mapping[str, object]],
    from_entity_ids: list[str] | None = None,
    to_entity_ids: list[str] | None = None,
    matrix_abbreviations: Mapping[str, str] | None = None,
) -> str:
    """Return markdown matrix table(s).

    When from_entity_ids/to_entity_ids are given, rows=from and cols=to (asymmetric matrix).
    Falls back to entity_ids for both axes when not provided.
    """
    row_ids = from_entity_ids if from_entity_ids is not None else entity_ids
    col_ids = to_entity_ids if to_entity_ids is not None else entity_ids
    if not row_ids or not col_ids or not connections:
        return ""

    active = [c for c in conn_type_configs if c.active]
    if not active:
        return ""

    from_set = frozenset(row_ids)
    to_set = frozenset(col_ids)

    conn_set: dict[str, set[tuple[str, str]]] = {}
    for conn in connections:
        src, tgt, ct = str(conn["source"]), str(conn["target"]), str(conn["conn_type"])
        if src in from_set and tgt in to_set:
            conn_set.setdefault(ct, set()).add((src, tgt))
        if conn.get("direction") == "symmetric" and tgt in from_set and src in to_set:
            conn_set.setdefault(ct, set()).add((tgt, src))

    if combined:
        return _combined_table(row_ids, col_ids, entity_names, active, conn_set, matrix_abbreviations or {})
    return "\n\n".join(_single_table(row_ids, col_ids, entity_names, cfg.conn_type, conn_set) for cfg in active)


#: What a cell holds where the two elements are not related. A non-breaking space, so that a renderer
#: draws the cell at all.
_EMPTY_MARK = "&nbsp;"


def _header(col_ids: list[str]) -> list[str]:
    """The corner cell, then each column's plain id — linkified by create_matrix."""
    return ["", *(escape_cell(entity_id) for entity_id in col_ids)]


def _row_cell(entity_id: str) -> str:
    return f"**{escape_cell(entity_id)}**"


def _single_table(
    row_ids: list[str],
    col_ids: list[str],
    entity_names: dict[str, str],
    conn_type: str,
    conn_set: dict[str, set[tuple[str, str]]],
) -> str:
    _ = entity_names  # available for future use
    pairs = conn_set.get(conn_type, set())
    rows = [
        [_row_cell(row_id), *("✓" if (row_id, col_id) in pairs else _EMPTY_MARK for col_id in col_ids)]
        for row_id in row_ids
    ]
    return "\n".join([f"## {conn_type}", "", format_table(_header(col_ids), rows)])


_LANG_PREFIXES = ("archimate-", "er-", "sequence-", "activity-", "usecase-")


def _abbreviations(
    active: list[ConnTypeConfig], ontology_abbreviations: Mapping[str, str]
) -> dict[str, str]:
    """Return abbreviation → conn_type using ontology declarations, falling back to
    auto-generation (strip language prefix, first letter uppercase) for unknown types."""
    abbrevs: dict[str, str] = {}
    used: set[str] = set()
    for cfg in active:
        ct = cfg.conn_type
        if ct in ontology_abbreviations:
            abbrevs[ct] = ontology_abbreviations[ct]
            used.add(ontology_abbreviations[ct])
        else:
            name = ct
            for pfx in _LANG_PREFIXES:
                if name.startswith(pfx):
                    name = name[len(pfx) :]
                    break
            candidate = name[0].upper()
            suffix = 2
            while candidate in used:
                candidate = f"{name[0].upper()}{suffix}"
                suffix += 1
            abbrevs[ct] = candidate
            used.add(candidate)
    return abbrevs


def _combined_table(
    row_ids: list[str],
    col_ids: list[str],
    entity_names: dict[str, str],
    active: list[ConnTypeConfig],
    conn_set: dict[str, set[tuple[str, str]]],
    ontology_abbreviations: Mapping[str, str],
) -> str:
    _ = entity_names  # available for future use
    abbrevs = _abbreviations(active, ontology_abbreviations)
    def marks(row_id: str, col_id: str) -> str:
        held = [abbrevs[cfg.conn_type] for cfg in active if (row_id, col_id) in conn_set.get(cfg.conn_type, set())]
        return ", ".join(held) or _EMPTY_MARK

    rows = [[_row_cell(row_id), *(marks(row_id, col_id) for col_id in col_ids)] for row_id in row_ids]

    def _strip_prefix(ct: str) -> str:
        for pfx in _LANG_PREFIXES:
            if ct.startswith(pfx):
                return ct[len(pfx) :]
        return ct

    legend = "*Legend: " + ", ".join(f"{abbrevs[cfg.conn_type]}={_strip_prefix(cfg.conn_type)}" for cfg in active) + "*"
    return format_table(_header(col_ids), rows) + "\n\n" + legend

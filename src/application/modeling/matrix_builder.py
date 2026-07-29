"""Generate markdown matrix tables from entity IDs and connection-type configs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


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


def _header_cell(entity_id: str) -> str:
    return entity_id  # plain ID — linkified by create_matrix


def _row_cell(entity_id: str) -> str:
    return f"**{entity_id}**"


def _single_table(
    row_ids: list[str],
    col_ids: list[str],
    entity_names: dict[str, str],
    conn_type: str,
    conn_set: dict[str, set[tuple[str, str]]],
) -> str:
    _ = entity_names  # available for future use
    pairs = conn_set.get(conn_type, set())
    header = "| | " + " | ".join(_header_cell(e) for e in col_ids) + " |"
    sep = "|---|" + "---|" * len(col_ids)
    rows = [f"## {conn_type}", "", header, sep]
    for row_id in row_ids:
        cells = ["✓" if (row_id, col_id) in pairs else "&nbsp;" for col_id in col_ids]
        rows.append("| " + _row_cell(row_id) + " | " + " | ".join(cells) + " |")
    return "\n".join(rows)


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
    header = "| | " + " | ".join(_header_cell(e) for e in col_ids) + " |"
    sep = "|---|" + "---|" * len(col_ids)
    rows = [header, sep]
    for row_id in row_ids:
        cells = []
        for col_id in col_ids:
            marks = [abbrevs[cfg.conn_type] for cfg in active if (row_id, col_id) in conn_set.get(cfg.conn_type, set())]
            cells.append(", ".join(marks) if marks else "&nbsp;")
        rows.append("| " + _row_cell(row_id) + " | " + " | ".join(cells) + " |")

    def _strip_prefix(ct: str) -> str:
        for pfx in _LANG_PREFIXES:
            if ct.startswith(pfx):
                return ct[len(pfx) :]
        return ct

    legend = "*Legend: " + ", ".join(f"{abbrevs[cfg.conn_type]}={_strip_prefix(cfg.conn_type)}" for cfg in active) + "*"
    return "\n".join(rows) + "\n\n" + legend

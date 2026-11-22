"""Progress, incidence and coverage derived from a document and its current naive architecture."""
from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from typing import Any

from src.application.artifacts.document_table_rows import DocumentTables
from src.application.change_sets.candidate_view import CandidateView


def _rows(tables: DocumentTables, name: str) -> list[dict[str, Any]]:
    table = tables.table(name)
    return [
        {"id": row.row_id, **{key: cell.value for key, cell in row.cells.items()}}
        for row in table.rows
    ] if table else []


def analyse(tables: DocumentTables, naive: CandidateView, *, kinds: tuple[str, ...] = ()) -> dict[str, Any]:
    stressors = _rows(tables, "stressors")
    ends = _rows(tables, "end-states")
    adaptations = _rows(tables, "adaptations")
    incidence = _rows(tables, "incidence")
    hits: dict[str, set[str]] = defaultdict(set)
    missing: dict[str, set[str]] = defaultdict(set)
    unexplained = []
    for tick in incidence:
        stressor, component = tick.get("stressor"), tick.get("component")
        if not stressor or not component:
            continue
        hits[stressor].add(component)
        if component not in naive.entities:
            missing[stressor].add(component)
        if not tick.get("note"):
            unexplained.append(tick["id"])
    for row in stressors:
        subject = row.get("subject")
        if subject and subject not in naive.entities:
            missing[row["id"]].add(subject)

    pairs = Counter(pair for components in hits.values() for pair in combinations(sorted(components), 2))
    counts = Counter(row["kind"] for row in stressors if row.get("kind"))
    grouped = Counter(row["end_state"] for row in stressors if row.get("end_state"))
    adapted = {end for row in adaptations for end in (row.get("end_states") or [])}
    touched = {component for components in hits.values() for component in components}
    fan_in = Counter(a.target_entity for a in naive.connections)
    fan_out = Counter(a.source_entity for a in naive.connections)
    return {
        "stressors": [{**row, "hits": sorted(hits[row["id"]]), "missing_elements": sorted(missing[row["id"]])}
                      for row in stressors],
        "end_states": ends, "adaptations": adaptations, "incidence": incidence,
        "coupling": [{"left": a, "right": b, "count": count} for (a, b), count in sorted(pairs.items())],
        "progress": {
            "unwalked": [row["id"] for row in stressors if not row.get("consequence")],
            "without_end_state": [row["id"] for row in stressors if not row.get("end_state")],
            "without_required_behaviour": [row["id"] for row in ends if not row.get("required_behaviour")],
            "without_adaptation": [
                row["id"] for row in ends if row["id"] not in adapted and not row.get("no_change_reason")
            ],
            "unexplained_hits": unexplained,
            "incomplete_rows": [
                {"table": table.spec.name, "row": row.row_id, "column": col.name}
                for table in tables.tables for row in table.rows for col in table.spec.columns
                if col.required and not row.cells[col.name].is_stated
            ],
        },
        "coverage": {
            "by_kind": dict(counts), "unused_kinds": sorted(set(kinds) - counts.keys()),
            "single_stressor_end_states": [row["id"] for row in ends if grouped[row["id"]] == 1],
            "untouched": [
                {"id": ref, "fan_in": fan_in[ref], "fan_out": fan_out[ref]}
                for ref in sorted(naive.entities.keys() - touched, key=lambda x: (-(fan_in[x] + fan_out[x]), x))
            ],
        },
    }

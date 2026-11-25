"""Progress, incidence and coverage derived from a document and its current naive architecture.

Every read here is of the design set. The test set is held apart from the work it judges: its
stressors, their ticks and the verdicts on them appear in none of these reads (see `evaluation`).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from typing import Any

from src.application.artifacts.document_table_rows import DocumentTables, TypedRow
from src.application.change_sets.candidate_view import CandidateView
from src.application.stress_analysis.rows import held_apart, rows_of
from src.domain.repository.repo_default_stress_perspectives import unwritten_perspectives


def _incomplete_design_rows(tables: DocumentTables, held: frozenset[str]) -> list[dict[str, str]]:
    """Each cell of a design row that is required and unstated, or stated and unreadable or unresolved."""
    return [
        {"table": table.spec.name, "row": row.row_id, "column": col.name}
        for table in tables.tables for row in table.rows
        if not _held_apart_row(table.spec.name, row, held)
        for col in table.spec.columns
        if (col.required and not row.cells[col.name].is_stated)
        or row.cells[col.name].unreadable or row.cells[col.name].unresolved
    ]


def _held_apart_row(table: str, row: TypedRow, held: frozenset[str]) -> bool:
    """Whether a row belongs to the test set: a verdict, a test stressor, or a tick of one."""
    match table:
        case "survival":
            return True
        case "stressors":
            return row.row_id in held
        case "incidence":
            return "stressor" in row.cells and row.cells["stressor"].value in held
        case _:
            return False


def analyse(tables: DocumentTables, naive: CandidateView) -> dict[str, Any]:
    held = held_apart(tables)
    stressors = [row for row in rows_of(tables, "stressors") if row["id"] not in held]
    ends = rows_of(tables, "end-states")
    adaptations = rows_of(tables, "adaptations")
    incidence = [tick for tick in rows_of(tables, "incidence") if tick.get("stressor") not in held]
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
            "incomplete_rows": _incomplete_design_rows(tables, held),
        },
        "coverage": {
            "by_kind": dict(counts), "unwritten_perspectives": unwritten_perspectives(counts),
            "single_stressor_end_states": [row["id"] for row in ends if grouped[row["id"]] == 1],
            "untouched": [
                {"id": ref, "fan_in": fan_in[ref], "fan_out": fan_out[ref]}
                for ref in sorted(naive.entities.keys() - touched, key=lambda x: (-(fan_in[x] + fan_out[x]), x))
            ],
        },
    }

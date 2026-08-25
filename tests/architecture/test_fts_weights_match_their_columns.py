"""Every bm25 weight list names exactly as many columns as its table has.

fts5 does not object to a short list. SQLite accepts it, treats the missing trailing weights as
nothing, and ranks — so the mistake is silent and the symptom is a ranking that makes no sense.

`scratchpad_notes_fts` had seven columns and six weights, and the list omitted the second
(`scratchpad_id`, carried UNINDEXED). Everything after it shifted by one: `scratchpad_id` absorbed the
4.0 meant for the note's title, the title took the body's 0.5, and `scratchpad_name` got nothing at
all. Measured on a two-row table: a note matched only on its *scratchpad's name* outranked a note
matched on its own **title**, both at ~1e-7. Aligning the list reversed the order and raised the
scores tenfold.

That is why this is a gate rather than a fix. One transposed list produced a plausible-looking result
set for as long as nobody compared two of them, and nothing in the schema or the query would have
said so.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_INDEX = Path("src/infrastructure/artifact_index")
_SCHEMA = _INDEX / "_sqlite_schema.py"
_QUERIES = _INDEX / "_sqlite_queries.py"
_WEIGHTS = _INDEX / "_fts_weights.py"


def _fts_columns() -> dict[str, int]:
    """Each `*_fts` table's declared column count, read from the DDL that creates it."""
    ddl = _SCHEMA.read_text(encoding="utf-8")
    tables: dict[str, int] = {}
    for match in re.finditer(
        r"CREATE VIRTUAL TABLE IF NOT EXISTS (\w+_fts) USING fts5\((.*?)\)", ddl, re.S
    ):
        name, body = match.group(1), match.group(2)
        # SQL comments first: a column list may be annotated, and a comma inside the prose would
        # otherwise be counted as a column. This gate exists to notice a miscount, so it must not
        # introduce one.
        columns = re.sub(r"--[^\n]*", "", body)
        tables[name] = len([part for part in columns.split(",") if part.strip()])
    return tables


def _weighted_calls() -> dict[str, int]:
    """Each `bm25(table, …)` call that passes weights, and how many it passes."""
    source = _QUERIES.read_text(encoding="utf-8")
    constants = {
        name: len([p for p in value.split(",") if p.strip()])
        for name, value in re.findall(
            r'^(\w*WEIGHTS)\s*=\s*"([^"]*)"', _WEIGHTS.read_text(encoding="utf-8"), re.M
        )
    }
    calls: dict[str, int] = {}
    for table, weights in re.findall(r"bm25\((\w+_fts),\s*\{(\w+)\}\)", source):
        assert weights in constants, f"bm25({table}) interpolates unknown {weights}"
        calls[table] = constants[weights]
    return calls


def test_the_schema_declares_the_tables_this_gate_checks() -> None:
    """Guards the guard: an extraction that found nothing would satisfy every assertion below."""
    assert _fts_columns(), "no fts5 tables found — the DDL extraction is broken"


@pytest.mark.parametrize("table", sorted(_weighted_calls()))
def test_a_weighted_query_passes_one_weight_per_column(table: str) -> None:
    columns = _fts_columns()
    assert table in columns, f"bm25 ranks {table}, which the schema does not create"

    assert _weighted_calls()[table] == columns[table], (
        f"{table} has {columns[table]} columns and its bm25 call passes "
        f"{_weighted_calls()[table]} weights. fts5 accepts the short list and shifts every weight "
        "after the omission onto the wrong column."
    )


def test_an_unweighted_query_is_a_deliberate_choice_not_an_omission() -> None:
    """A table ranked without weights gives every column 1.0, which is a decision about ranking —
    a title weighing the same as the content. Listed so adding a table cannot inherit it silently."""
    source = _QUERIES.read_text(encoding="utf-8")
    unweighted = set(re.findall(r"bm25\((\w+_fts)\)", source))

    assert unweighted == {"connections_fts", "documents_fts"}, (
        f"the set of unweighted fts tables changed: {sorted(unweighted)}. Either weight the new one "
        "or add it here with the reason its columns rank equally."
    )

"""The keyword index's answer to a search: which records match, and which of them each kind admits.

Its own module because it is one question with its own policy — what a typed query matches, which
rows fill each kind's window, who may be seen — and `_sqlite_queries.py` had passed the source-length
limit answering it beside the graph and context reads.
"""

from __future__ import annotations

import sqlite3

from src.application.artifacts.scoring import tokenize
from src.domain.search_records import KeywordRow, TitleAdmission

from ._fts_weights import DIAGRAM_WEIGHTS, ENTITY_WEIGHTS, NOTE_WEIGHTS, SCRATCHPAD_WEIGHTS


def _entity_visibility_filter(
    excluded_entity_types: frozenset[str], visible_diagram_entity_types: frozenset[str] | None
) -> tuple[str, tuple[str, ...]]:
    """Prepared visibility filter, applied before the per-kind LIMIT.

    Both halves of the eligibility policy, rendered as SQL from the sets the application hands over:
    an excluded *type* never matches, and a *diagram-owned* record matches only if its type opted in.
    A record with no `host_diagram_id` is a model entity and passes regardless.

    It runs here, inside the subquery, rather than over the returned rows, because a row filtered
    afterwards has already spent a slot: the same query answered with sixteen rows of twenty because
    four invisible records were ranked first and then removed. `host_diagram_id` is carried UNINDEXED
    on the FTS table for exactly this.
    """
    clauses: list[str] = []
    params: list[str] = []
    if excluded_entity_types:
        clauses.append(f" AND artifact_type NOT IN ({','.join('?' * len(excluded_entity_types))})")
        params.extend(sorted(excluded_entity_types))
    # `None` and an empty set are different instructions. `None` is a caller not applying the
    # ownership policy — a direct index query — and adds no clause. An empty set is the policy applied
    # with nothing opted in, and admits only records with no host diagram.
    if visible_diagram_entity_types is not None:
        opted_in = ",".join("?" * len(visible_diagram_entity_types))
        clauses.append(
            f" AND (host_diagram_id = '' OR artifact_type IN ({opted_in}))"
            if opted_in
            else " AND host_diagram_id = ''"
        )
        params.extend(sorted(visible_diagram_entity_types))
    return "".join(clauses), tuple(params)


def _typed_match(tokens: list[str]) -> str:
    """The fts5 query for what a reader typed: any of the words, the last one possibly unfinished.

    A search box is answered while it is being typed, so its last word is usually a prefix of the word
    meant. Matched whole, `Artifact Ind` asked for *artifact* or the nonexistent word *ind*, and the
    title being spelt could not be told from any other record mentioning artifacts.
    """
    *whole, last = tokens
    return " OR ".join([*(f'"{token}"' for token in whole), f'"{last}"*'])


def _title_admission(table: str, title_column: str | None, tokens: list[str]) -> tuple[str, tuple[str, ...]]:
    """An ORDER BY key that puts a kind's title matches first, so its LIMIT cannot drop them.

    Evaluates to a `TitleAdmission`: a title that *begins* with the typed words (the last possibly
    unfinished), one in which every typed word begins *some* word, or neither. The first is a subset
    of the second, so the two memberships add up to the level.

    A title the reader is typing is the strongest evidence a row can carry, and `rank_hits` puts it
    above every score — but only if the row reaches it. Ordered by bm25 alone, the per-kind window
    filled with records whose *bodies* repeat a common word, and the one whose title the reader was
    typing fell outside it. Which rows to admit is decided here, against the window being filled; how
    the admitted rows rank is the application's question, and it asks it again.

    Every such row also matches `_typed_match`, which ORs the same words with the last as a prefix,
    so this orders the window and never widens it.
    """
    if title_column is None:
        return "0", ()
    phrase = " ".join(tokens)
    beginning = f'{title_column} : ^"{phrase}"*'
    every_word = f"{title_column} : (" + " AND ".join(f'"{token}"*' for token in tokens) + ")"
    member = f"(rowid IN (SELECT rowid FROM {table} WHERE {table} MATCH ?))"
    return f"({member} + {member})", (beginning, every_word)


def _closeness(title_column: str | None) -> str:
    """Among titles that begin with what was typed, the shortest first: it is the closest to it.

    The exact title is the shortest of them all, and it is the one a reader who typed it in full is
    asking for. Ordered by bm25 instead, `Architect` was crowded out of its own window by a dozen
    `Architecture …` records whose bodies say *architecture* more often. The other admission levels
    have no such order and keep their score's.
    """
    if title_column is None:
        return "NULL"
    return f"CASE WHEN title_admission = {int(TitleAdmission.BEGINNING)} THEN length({title_column}) END"


def search_fts(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int,
    kinds: frozenset[str],
    excluded_entity_types: frozenset[str] = frozenset(),
    visible_diagram_entity_types: frozenset[str] | None = None,
    fts_enabled: bool,
) -> list[KeywordRow]:
    tokens = tokenize(query.lower())
    if not tokens or not fts_enabled:
        return []
    match_query = _typed_match(tokens)
    per_kind_limit = max(limit, 1)
    entity_filter_sql, entity_filter_params = _entity_visibility_filter(
        excluded_entity_types, visible_diagram_entity_types
    )
    # Per-kind subqueries each get their own ORDER BY + LIMIT so that a dominant
    # kind (e.g. hundreds of entity hits) cannot crowd out minority kinds.
    # The fifth field is the kind's title column, or None for a kind with no title.
    kind_rows: list[tuple[str, str, str, str, str | None, str, tuple[str, ...]]] = [
        ("entities", "entity", "entities_fts", f"-bm25(entities_fts, {ENTITY_WEIGHTS})", "name",
         entity_filter_sql, entity_filter_params),
        ("connections", "connection", "connections_fts", "-bm25(connections_fts)", None, "", ()),
        ("diagrams", "diagram", "diagrams_fts", f"-bm25(diagrams_fts, {DIAGRAM_WEIGHTS})", "name", "", ()),
        ("documents", "document", "documents_fts", "-bm25(documents_fts)", "title", "", ()),
        ("scratchpads", "scratchpad", "scratchpads_fts", f"-bm25(scratchpads_fts, {SCRATCHPAD_WEIGHTS})",
         "name", "", ()),
        ("scratchpad-notes", "scratchpad-note", "scratchpad_notes_fts",
         f"-bm25(scratchpad_notes_fts, {NOTE_WEIGHTS})", "title", "", ()),
    ]
    subqueries: list[str] = []
    params: list[str] = []
    for kind, record_type, table, score_expr, title_column, filter_sql, filter_params in kind_rows:
        if kind not in kinds:
            continue
        title_sql, title_params = _title_admission(table, title_column, tokens)
        subqueries.append(
            f"SELECT artifact_id, '{record_type}' AS record_type, {score_expr} AS score, "
            f"{title_sql} AS title_admission "
            f"FROM {table} WHERE {table} MATCH ?{filter_sql} "
            f"ORDER BY title_admission DESC, {_closeness(title_column)}, score DESC LIMIT {per_kind_limit}"
        )
        params.extend(title_params)
        params.append(match_query)
        params.extend(filter_params)
    if not subqueries:
        return []
    sql = (
        "SELECT artifact_id, record_type, score, title_admission FROM ("
        + " UNION ALL ".join(f"SELECT * FROM ({sq})" for sq in subqueries)
        + ") ORDER BY score DESC, artifact_id ASC"
    )
    rows = conn.execute(sql, params).fetchall()
    return [
        KeywordRow(
            str(r["artifact_id"]), str(r["record_type"]), float(r["score"]), TitleAdmission(r["title_admission"])
        )
        for r in rows
    ]

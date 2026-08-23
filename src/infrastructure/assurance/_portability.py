"""Bulk export/import of the confidential assurance graph (portability + seeding).

`export_bundle` collects analyses, nodes, edges, arch-refs and factor assessments;
`import_bundle` restores them into whatever store the environment provisions. Ids are preserved
verbatim so edges and arch-refs keep resolving — the round-trip reconstructs an identical graph,
re-encrypted under the target store's own key. The columns an import may write are read from the
target schema, which keeps the dynamic SQL injection-safe and stops the importer falling behind a
column the exporter emits; parents are inserted before children so the foreign-key constraints
hold.

**Factor assessments are part of the graph, not a derived view of it.** They were once omitted, and
that omission was the dangerous kind: severity and detectability are derived and come back on their
own, while occurrence is asserted-only, so an export without assessments silently drops the one
half of the analysis nobody can recompute — each judgement's value, its rationale, and who made it.
This bundle is the only durable copy of a store whose archive lives inside its own encryption, so
what it leaves out is simply lost.

**Filing and participation are carried for the same reason.** A group is where an analyst decided
an analysis belongs, and a membership is one method's decision to reason over another's nodes.
Neither is recoverable from the nodes and edges: an FMEA that lost its memberships still lists
failure modes, but nothing records that they were raised against the control structure an STPA
built.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.infrastructure.assurance._archive import append_audit_row

if TYPE_CHECKING:
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore

#: Tables the bundle restores, keyed by the bundle section that feeds each one.
#: The columns are deliberately NOT listed here. A hand-maintained allowlist has to be edited
#: every time the schema grows a column, and an unedited one drops that column silently while
#: still reporting a full row count — a column such as `failure_type`, the FMEA guideword that
#: decides which matrix cell a failure mode occupies. Reading the columns from the target schema
#: cannot drift from it, and keeps the dynamic SQL just as injection-safe: every interpolated
#: name comes from PRAGMA table_info, never from the bundle.
_SECTION_TABLES: tuple[tuple[str, str], ...] = (
    ("groups", "assurance_groups"),
    ("analyses", "assurance_analyses"),
    ("nodes", "assurance_nodes"),
    ("edges", "assurance_edges"),
    ("arch_refs", "arch_refs"),
    ("factor_assessments", "fmea_factor_assessments"),
    ("analysis_members", "assurance_analysis_members"),
)

# Children before parents on delete; parents before children on insert (FK-safe ordering).
# Assessments are listed first for the same reason the edges are: a replace that left them behind
# would orphan judgements against deleted nodes, and a later node reusing an id would inherit them.
#
# `audit_log` and `baselines` are absent from both this and `_SECTION_TABLES`, and that is the whole
# design: the chain belongs to the store rather than to the graph it describes. So an import neither
# clears the history that is there — which is what makes a re-seed auditable rather than a gap — nor
# carries another store's hashes in and presents them as this one's.
_DELETE_ORDER = (
    "fmea_factor_assessments", "assurance_analysis_members", "assurance_edges", "arch_refs",
    "assurance_nodes", "assurance_analyses", "assurance_groups",
)

#: The archive operation an import appends. Replacing the graph is the largest single mutation the
#: store has, and it was the one operation the chain did not record.
_IMPORT_OPERATION = "IMPORT_BUNDLE"


def _row_counts(conn: object, tables: tuple[str, ...]) -> dict[str, int]:
    """How many rows each table holds. Read before a replace deletes them, so the archive entry can
    say what was destroyed rather than only that something was."""
    counts: dict[str, int] = {}
    for table in tables:
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()  # type: ignore[attr-defined]
        counts[table] = int(row["n"])
    return counts


def export_bundle(store: SQLCipherAssuranceStore) -> dict[str, list[dict[str, object]]]:
    """Collect the full assurance graph as plain dict rows. Requires an unlocked store."""
    if not store.is_unlocked():
        raise RuntimeError("Store must be unlocked before export.")
    nodes = store.list_nodes()
    by_node = store.read_fmea_assessments([str(n["node_id"]) for n in nodes])
    return {
        "groups": store.list_groups(),
        "analyses": store.list_analyses(),
        "nodes": nodes,
        "edges": store.list_edges(),
        "arch_refs": store.list_arch_refs(),
        "factor_assessments": [row for rows in by_node.values() for row in rows],
        "analysis_members": store.list_all_analysis_members(),
    }


def table_columns(conn: object, table: str) -> tuple[str, ...]:
    """The target table's own column names, in declaration order.

    The single source of truth for what an import may write, and the only strings
    interpolated into the INSERT — they come from the schema, never from the bundle.
    """
    # The store's connection yields mapping rows; PRAGMA's column-name field is "name".
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()  # type: ignore[attr-defined]
    return tuple(str(row["name"]) for row in rows)


def _insert_rows(conn: object, table: str, cols: tuple[str, ...], rows: list[dict[str, object]]) -> int:
    written = 0
    for row in rows:
        present = [c for c in cols if c in row]
        if not present:
            continue
        placeholders = ", ".join(["?"] * len(present))
        conn.execute(  # type: ignore[attr-defined]
            f"INSERT OR REPLACE INTO {table} ({', '.join(present)}) VALUES ({placeholders})",
            [row[c] for c in present],
        )
        written += 1
    return written


def import_bundle(
    store: SQLCipherAssuranceStore,
    bundle: dict[str, list[dict[str, object]]],
    *,
    replace: bool = False,
    source: str = "",
) -> dict[str, int]:
    """Insert an exported bundle into *store*, preserving ids. Requires an unlocked store.

    With ``replace=True`` the existing graph is cleared first (children before parents) so
    a re-seed is idempotent rather than additive.

    *source* names where the bundle came from, for the archive entry. It is recorded rather than
    used, and an empty one is honest about a caller that has no path to give.

    **The import records itself**, in the same transaction as the rows it writes. Replacing the graph
    deletes every node, edge, arch ref, membership and factor assessment, and until this was appended
    the chain said none of that had happened: the archive read *analysis created, nodes assigned
    provenance* and then held nothing to explain why the store showed neither. Effects with no
    recorded cause is what a tamper-evident log exists to make impossible, so the omission was in the
    one operation that most needed the entry.
    """
    if not store.is_unlocked():
        raise RuntimeError("Store must be unlocked before import.")
    conn = store.unlocked_connection()
    cleared = _row_counts(conn, _DELETE_ORDER) if replace else {}
    if replace:
        for table in _DELETE_ORDER:
            conn.execute(f"DELETE FROM {table}")
    counts = {
        section: _insert_rows(conn, table, table_columns(conn, table), bundle.get(section, []))
        for section, table in _SECTION_TABLES
    }
    # Appended, not committed, by the chained writer — so the entry and the rows it describes land
    # together or not at all. A separate commit could leave a recorded import that did not happen.
    append_audit_row(
        conn,
        _IMPORT_OPERATION,
        payload={
            "source": source,
            "replace": replace,
            "cleared": {table: n for table, n in cleared.items() if n},
            "inserted": {section: n for section, n in counts.items() if n},
        },
    )
    conn.commit()  # type: ignore[attr-defined]
    return counts

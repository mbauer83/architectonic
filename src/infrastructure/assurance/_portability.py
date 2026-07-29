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
_DELETE_ORDER = (
    "fmea_factor_assessments", "assurance_analysis_members", "assurance_edges", "arch_refs",
    "assurance_nodes", "assurance_analyses", "assurance_groups",
)


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
) -> dict[str, int]:
    """Insert an exported bundle into *store*, preserving ids. Requires an unlocked store.

    With ``replace=True`` the existing graph is cleared first (children before parents) so
    a re-seed is idempotent rather than additive.
    """
    if not store.is_unlocked():
        raise RuntimeError("Store must be unlocked before import.")
    conn = store.unlocked_connection()
    if replace:
        for table in _DELETE_ORDER:
            conn.execute(f"DELETE FROM {table}")
    counts = {
        section: _insert_rows(conn, table, table_columns(conn, table), bundle.get(section, []))
        for section, table in _SECTION_TABLES
    }
    conn.commit()  # type: ignore[attr-defined]
    return counts

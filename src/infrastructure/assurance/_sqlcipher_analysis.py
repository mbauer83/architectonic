"""SQLCipher persistence for the assurance analysis aggregate.

Free functions over an open sqlcipher3 connection; the store adapter delegates
its analysis CRUD here to stay focused and within the per-file size budget.
"""

from __future__ import annotations

from typing import Any

from src.infrastructure.assurance import _analysis_records as analyses
from src.infrastructure.assurance._id_utils import make_group_id
from src.infrastructure.assurance._sqlcipher_util import now_iso, where


def create(
    conn: Any,
    name: str,
    method: str,
    architecture_anchor_id: str = "",
    *,
    tlp: str,
    status: str,
) -> str:
    rec = analyses.new_analysis_record(name, method, architecture_anchor_id, tlp=tlp, status=status)
    conn.execute(
        "INSERT INTO assurance_analyses "
        "(analysis_id, name, method, architecture_anchor_id, status, tlp, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            rec["analysis_id"], rec["name"], rec["method"], rec["architecture_anchor_id"],
            rec["status"], rec["tlp"], rec["created_at"], rec["updated_at"],
        ),
    )
    conn.commit()
    return str(rec["analysis_id"])


def get(conn: Any, analysis_id: str) -> dict[str, object] | None:
    row = conn.execute(
        "SELECT * FROM assurance_analyses WHERE analysis_id = ?", (analysis_id,)
    ).fetchone()
    return row if row else None


def list_analyses(
    conn: Any,
    *,
    method: str | None = None,
    status: str | None = None,
) -> list[dict[str, object]]:
    clause, params = where({"method": method, "status": status})
    rows = conn.execute(
        f"SELECT * FROM assurance_analyses {clause} ORDER BY created_at", params
    ).fetchall()
    return list(rows)


def delete(conn: Any, analysis_id: str) -> None:
    """Delete an analysis and the participation rows naming it, as one unit of work.

    Participation has no foreign key to analyses, so deleting only the analysis leaves rows that
    name something absent — and an analysis that merely *borrowed* nodes leaves one per borrowed
    node. Two statements, one commit: an application-layer loop between them could be interrupted
    and leave exactly the orphans this prevents.

    The nodes themselves and their provenance are untouched. Participation says another analysis
    drew on their work; the analysis going away ends that relation, not the work.
    """
    conn.execute(
        "DELETE FROM assurance_analysis_members WHERE analysis_id = ?", (analysis_id,)
    )
    conn.execute("DELETE FROM assurance_analyses WHERE analysis_id = ?", (analysis_id,))
    conn.commit()


def update(conn: Any, analysis_id: str, attrs: dict[str, object]) -> None:
    sets: list[str] = ["updated_at = ?"]
    params: list[object] = [now_iso()]
    for key, value in attrs.items():
        if key in analyses.ANALYSIS_UPDATABLE:
            sets.append(f"{key} = ?")
            params.append(value)
    params.append(analysis_id)
    conn.execute(
        f"UPDATE assurance_analyses SET {', '.join(sets)} WHERE analysis_id = ?", params
    )
    conn.commit()


# ── Grouping: filing above analyses ───────────────────────────────────────────


def create_group(conn: Any, name: str, description: str = "") -> str:
    group_id = make_group_id(name)
    now = now_iso()
    conn.execute(
        "INSERT INTO assurance_groups (group_id, name, description, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (group_id, name, description, now, now),
    )
    conn.commit()
    return group_id


def get_group(conn: Any, group_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM assurance_groups WHERE group_id = ?", (group_id,)
    ).fetchone()
    return row if row else None


def list_groups(conn: Any) -> list[dict[str, Any]]:
    return list(conn.execute("SELECT * FROM assurance_groups ORDER BY name").fetchall())


def delete_group(conn: Any, group_id: str) -> None:
    """Delete the group and unfile its analyses.

    Never cascades to the analyses themselves. A group is filing, and deleting a folder that
    happens to contain a hazard analysis must not delete the hazard analysis — the two are the
    same gesture in a UI and must not be the same gesture in the store.
    """
    conn.execute("UPDATE assurance_analyses SET group_id = NULL WHERE group_id = ?", (group_id,))
    conn.execute("DELETE FROM assurance_groups WHERE group_id = ?", (group_id,))
    conn.commit()


# ── Participation: a node taking part in an analysis that did not author it ───


def add_member(conn: Any, analysis_id: str, node_id: str) -> None:
    """Draw an existing node into another analysis.

    Idempotent, because "make sure this participates" is the operation callers actually want;
    adding the same control-structure node to an FMEA twice is not an error worth surfacing.
    """
    conn.execute(
        "INSERT OR IGNORE INTO assurance_analysis_members (analysis_id, node_id, added_at) "
        "VALUES (?, ?, ?)",
        (analysis_id, node_id, now_iso()),
    )
    conn.commit()


def remove_member(conn: Any, analysis_id: str, node_id: str) -> None:
    """Stop a node participating. The node itself is untouched — it still exists, and the
    analysis that authored it still owns it."""
    conn.execute(
        "DELETE FROM assurance_analysis_members WHERE analysis_id = ? AND node_id = ?",
        (analysis_id, node_id),
    )
    conn.commit()


def remove_all_members_of_node(conn: Any, node_id: str) -> None:
    """Drop every membership naming this node, for use when the node itself is being deleted.

    No commit: this is one step of `delete_node`'s unit of work, and a membership that outlived
    its node by the width of a failed transaction is exactly the orphan being prevented.
    """
    conn.execute("DELETE FROM assurance_analysis_members WHERE node_id = ?", (node_id,))


def list_members(conn: Any, analysis_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT node_id FROM assurance_analysis_members WHERE analysis_id = ? ORDER BY added_at",
        (analysis_id,),
    ).fetchall()
    return [str(row["node_id"]) for row in rows]


def list_all_members(conn: Any) -> list[dict[str, Any]]:
    """Every membership row, whole. Participation is graph content, so the portability bundle —
    the only durable copy of a store whose archive lives inside its own encryption — has to carry
    it; ids alone would lose when each was granted."""
    return list(
        conn.execute(
            "SELECT * FROM assurance_analysis_members ORDER BY analysis_id, added_at"
        ).fetchall()
    )


def participating_analyses(conn: Any, node_id: str) -> list[str]:
    """Analyses that draw on this node, excluding the one that authored it — authorship lives
    on the node and is not duplicated here."""
    rows = conn.execute(
        "SELECT analysis_id FROM assurance_analysis_members WHERE node_id = ? ORDER BY added_at",
        (node_id,),
    ).fetchall()
    return [str(row["analysis_id"]) for row in rows]

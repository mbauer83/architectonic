"""Filing and participation persistence, shared by every confidential-store backend.

Two relations live here, and they answer different questions from the ones `analysis_id` on a
node answers:

* **A group files analyses.** Flat, with no method of its own — which is what distinguishes a
  group from the analyses it holds. Deleting a group unfiles its analyses and never deletes
  them: filing and content are the same gesture in a UI and must not be the same gesture in
  the store.
* **A membership records participation.** Many-to-many, so an FMEA can enumerate failure modes
  against the control-structure nodes an STPA authored without copying them — and the copies
  then cannot drift, because there are none.

Authorship stays on the node (`assurance_nodes.analysis_id`) and is deliberately not repeated
here. One value cannot answer both *who made this* and *who uses this*, and answering both with
one forbids the synergy that makes running two methods worthwhile.

Each backend gets a mixin rather than a copy of the logic, following the arrangement the analysis
aggregate and the factor assessments already use: record shape and ordering live here once, and
each mixin supplies only the part that differs. The file-backed mixin is below; the REST one is in
`_pocketbase_grouping`, beside the analysis collection it has to refile; and SQLCipher keeps its
SQL in `_sqlcipher_analysis`, where the join table it indexes is declared.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.domain.clock import utc_now_iso as _now_iso
from src.infrastructure.assurance._analysis_records import (
    ANALYSES_DIR,
    list_analyses_files,
    update_analysis_file,
)
from src.infrastructure.assurance._id_utils import make_group_id

#: Directory names used by the file-backed backends.
GROUPS_DIR = "groups"
MEMBERS_DIR = "analysis-members"

#: Collection names used by the REST backend.
GROUPS_COLLECTION = "assurance_groups"
MEMBERS_COLLECTION = "assurance_analysis_members"


def new_group_record(name: str, description: str = "") -> dict[str, object]:
    """Build a fully-populated group record (id + timestamps assigned here)."""
    now = _now_iso()
    return {
        "group_id": make_group_id(name),
        "name": name,
        "description": description,
        "created_at": now,
        "updated_at": now,
    }


def new_member_record(analysis_id: str, node_id: str) -> dict[str, object]:
    return {"analysis_id": analysis_id, "node_id": node_id, "added_at": _now_iso()}


def member_filename(analysis_id: str, node_id: str) -> str:
    """One file per pair, named after both ids, as the architecture references are.

    A file per pair is what makes ``add_analysis_member`` idempotent without reading anything:
    the same pair resolves to the same name.
    """
    return f"{analysis_id}__{node_id}"


def sorted_by_name(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Groups in the order a reader expects to file into them."""
    return sorted(groups, key=lambda group: str(group.get("name", "")))


def sorted_by_added(members: list[dict[str, Any]]) -> list[str]:
    """Member node ids oldest first — the order participation was granted in."""
    ordered = sorted(members, key=lambda member: str(member.get("added_at", "")))
    return [str(member["node_id"]) for member in ordered]


class FileGroupingStoreMixin:
    """Groups as one file per group, memberships as one file per (analysis, node) pair.

    Reuses the host store's own `_read`/`_write` pair, so the plain and encrypted variants differ
    only by the file extension they declare — the encrypted store's filing is encrypted by the
    same code path as its nodes.

    Refiling reaches the analysis records through `_analysis_records`' free functions rather than
    through `self.update_analysis`. The two are equivalent only while the mixins happen to be
    ordered so that the analysis mixin wins the lookup; naming the collaborator makes the
    dependency real instead of a property of the base-class list.
    """

    #: File extension the host store persists with (`json` plain, `enc` encrypted).
    _ANALYSIS_EXT: str = "json"

    _repo: Path

    def _require_unlocked(self) -> None:
        raise NotImplementedError("provided by the host store")

    def _read(self, path: Path) -> dict[str, object] | None:
        raise NotImplementedError("provided by the host store")

    def _write(self, path: Path, data: dict[str, object]) -> None:
        raise NotImplementedError("provided by the host store")

    # ── Directories ───────────────────────────────────────────────────────────

    def _groups_dir(self) -> Path:
        return self._ensured(self._repo / GROUPS_DIR)

    def _members_dir(self) -> Path:
        return self._ensured(self._repo / MEMBERS_DIR)

    def _ensured(self, directory: Path) -> Path:
        # Created on demand rather than at unlock alone, so a store initialised before filing
        # existed gains the directories on first use instead of raising.
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _records_in(self, directory: Path, key: str) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        for path in sorted(directory.glob(f"*.{self._ANALYSIS_EXT}")):
            record = self._read(path)
            # A directory an operator manages can hold anything; one unreadable file must not
            # take down a read that a person is waiting on.
            if isinstance(record, dict) and key in record:
                found.append(record)
        return found

    # ── Groups ────────────────────────────────────────────────────────────────

    def create_group(self, name: str, description: str = "") -> str:
        self._require_unlocked()
        record = new_group_record(name, description)
        group_id = str(record["group_id"])
        self._write(self._groups_dir() / f"{group_id}.{self._ANALYSIS_EXT}", record)
        return group_id

    def get_group(self, group_id: str) -> dict[str, object] | None:
        self._require_unlocked()
        return self._read(self._groups_dir() / f"{group_id}.{self._ANALYSIS_EXT}")

    def list_groups(self) -> list[dict[str, object]]:
        self._require_unlocked()
        return sorted_by_name(self._records_in(self._groups_dir(), "group_id"))

    def delete_group(self, group_id: str) -> None:
        """Remove the group and unfile its analyses. Their content is untouched."""
        self._require_unlocked()
        analyses_dir = self._repo / ANALYSES_DIR
        filed = list_analyses_files(
            self._read, analyses_dir, self._ANALYSIS_EXT, method=None, status=None
        )
        for analysis in filed:
            if str(analysis.get("group_id") or "") == group_id:
                update_analysis_file(
                    self._read, self._write, analyses_dir, self._ANALYSIS_EXT,
                    str(analysis["analysis_id"]), {"group_id": None},
                )
        (self._groups_dir() / f"{group_id}.{self._ANALYSIS_EXT}").unlink(missing_ok=True)

    # ── Participation ─────────────────────────────────────────────────────────

    def _member_path(self, analysis_id: str, node_id: str) -> Path:
        name = member_filename(analysis_id, node_id)
        return self._members_dir() / f"{name}.{self._ANALYSIS_EXT}"

    def add_analysis_member(self, analysis_id: str, node_id: str) -> None:
        """Draw an existing node into another analysis. Idempotent — "make sure this
        participates" is the operation callers actually want."""
        self._require_unlocked()
        path = self._member_path(analysis_id, node_id)
        if not path.exists():
            self._write(path, new_member_record(analysis_id, node_id))

    def remove_analysis_member(self, analysis_id: str, node_id: str) -> None:
        self._require_unlocked()
        self._member_path(analysis_id, node_id).unlink(missing_ok=True)

    def remove_all_analysis_members_of_node(self, node_id: str) -> None:
        """Drop every membership naming this node, for use when the node itself is deleted.

        Both file-backed stores get this from here rather than each dropping its own participation
        files, for the reason the mixin exists: the pair naming lives in one place, so a store
        cannot delete by a convention that has drifted from the one it wrote with.
        """
        self._require_unlocked()
        for record in self._records_in(self._members_dir(), "node_id"):
            if str(record.get("node_id", "")) == node_id:
                self._member_path(str(record.get("analysis_id", "")), node_id).unlink(missing_ok=True)

    def list_analysis_members(self, analysis_id: str) -> list[str]:
        self._require_unlocked()
        return sorted_by_added([
            record for record in self._records_in(self._members_dir(), "node_id")
            if str(record.get("analysis_id", "")) == analysis_id
        ])

    def list_participating_analyses(self, node_id: str) -> list[str]:
        self._require_unlocked()
        records = [
            record for record in self._records_in(self._members_dir(), "analysis_id")
            if str(record.get("node_id", "")) == node_id
        ]
        ordered = sorted(records, key=lambda record: str(record.get("added_at", "")))
        return [str(record["analysis_id"]) for record in ordered]


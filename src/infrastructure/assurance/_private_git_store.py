"""Private-git-backed confidential assurance store adapter.

Persists assurance nodes, edges, and architecture cross-references as JSON files
under a directory tree that the user manages as a private git repository.

Layout:
  {repo_path}/nodes/{node_id}.json
  {repo_path}/edges/{edge_id}.json
  {repo_path}/refs/{assurance_node_id}__{ref_type}__{arch_artifact_id}.json

The adapter handles file I/O only; git operations (add/commit/push) are the
caller's responsibility.  The double-underscore separator is safe because all
existing ID formats use single `@`, `.`, and alphanumeric characters.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.application.assurance.node_sorting import sorted_node_dicts
from src.domain.assurance.arch_ref_identity import refs_to_retarget
from src.domain.assurance.assurance_node_types import NODE_UPDATABLE
from src.domain.assurance.node_search import rank_node_matches
from src.domain.clock import utc_now_iso as _now_iso
from src.infrastructure.assurance._analysis_records import ANALYSES_DIR, FileAnalysisStoreMixin
from src.infrastructure.assurance._edge_records import as_arch_ref_records, as_edge_records
from src.infrastructure.assurance._fmea_assessment_records import (
    FMEA_ASSESSMENTS_DIR,
    FileFmeaAssessmentMixin,
)
from src.infrastructure.assurance._grouping_records import (
    GROUPS_DIR,
    MEMBERS_DIR,
    FileGroupingStoreMixin,
)
from src.infrastructure.assurance._id_utils import make_edge_id, make_node_id
from src.infrastructure.assurance._node_records import as_node_record, as_node_records

logger = logging.getLogger(__name__)

_LOCKED_MSG = "Assurance store is locked. Call unlock() first."


def _ref_filename(assurance_node_id: str, ref_type: str, arch_artifact_id: str) -> str:
    return f"{assurance_node_id}__{ref_type}__{arch_artifact_id}.json"


class PrivateGitAssuranceStore(
    FileAnalysisStoreMixin, FileGroupingStoreMixin, FileFmeaAssessmentMixin
):
    """Adapter implementing ConfidentialAssuranceStore backed by a local directory tree.

    Suitable for teams using a private git repository as their assurance store.
    All writes are atomic (write to temp then rename) where the filesystem supports it.
    """

    _ANALYSIS_EXT = "json"

    def __init__(self, repo_path: Path) -> None:
        self._repo = repo_path
        self._unlocked = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def is_unlocked(self) -> bool:
        return self._unlocked

    def unlock(self) -> None:
        self._repo.mkdir(parents=True, exist_ok=True)
        for subdir in (
            "nodes", "edges", "refs", ANALYSES_DIR, GROUPS_DIR, MEMBERS_DIR,
            FMEA_ASSESSMENTS_DIR,
        ):
            (self._repo / subdir).mkdir(exist_ok=True)
        self._unlocked = True
        logger.info("Private-git store unlocked at %s", self._repo)

    def lock(self) -> None:
        self._unlocked = False

    def _require_unlocked(self) -> None:
        if not self._unlocked:
            raise RuntimeError(_LOCKED_MSG)

    def _write(self, path: Path, data: dict[str, object]) -> None:
        import os  # noqa: PLC0415
        import tempfile  # noqa: PLC0415

        text = json.dumps(data, indent=2)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, path)
        except Exception:  # noqa: BLE001
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _read(self, path: Path) -> dict[str, object] | None:
        if not path.exists():
            return None
        return json.loads(path.read_text())  # type: ignore[return-value]

    # ── Analysis aggregate ─ provided by FileAnalysisStoreMixin (analyses/*.json) ─

    # ── Node CRUD ─────────────────────────────────────────────────────────────

    def get_node(self, node_id: str) -> dict[str, object] | None:
        self._require_unlocked()
        record = self._read(self._repo / "nodes" / f"{node_id}.json")
        return None if record is None else as_node_record(record)

    def list_nodes(
        self,
        *,
        node_type: str | None = None,
        status: str | None = None,
        concern_class: str | None = None,
        tlp: str | None = None,
        analysis_id: str | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> list[dict[str, object]]:
        self._require_unlocked()
        nodes: list[dict[str, object]] = []
        for path in sorted((self._repo / "nodes").glob("*.json")):
            node = json.loads(path.read_text())
            if node_type and node.get("node_type") != node_type:
                continue
            if status and node.get("status") != status:
                continue
            if concern_class and node.get("concern_class") != concern_class:
                continue
            if tlp and node.get("tlp") != tlp:
                continue
            if analysis_id and node.get("analysis_id") != analysis_id:
                continue
            nodes.append(node)
        return as_node_records(sorted_node_dicts(nodes, sort, order))

    def create_node(
        self,
        node_type: str,
        name: str,
        *,
        status: str = "draft",
        tlp: str = "TLP:WHITE",
        concern_class: str | None = None,
        disposition: str | None = None,
        uca_type: str | None = None,
        failure_type: str | None = None,
        mode: str | None = None,
        binding_status: str | None = None,
        node_role: str | None = None,
        analysis_id: str | None = None,
        attributes: dict[str, object] | None = None,
        content: str = "",
    ) -> str:
        self._require_unlocked()
        node_id = make_node_id(node_type, name)
        now = _now_iso()
        data: dict[str, object] = {
            "node_id": node_id, "node_type": node_type, "name": name,
            "status": status, "tlp": tlp, "concern_class": concern_class,
            "disposition": disposition, "uca_type": uca_type,
            "failure_type": failure_type, "mode": mode,
            "binding_status": binding_status, "node_role": node_role,
            "analysis_id": analysis_id,
            "attributes_json": json.dumps(attributes or {}),
            "content_text": content, "created_at": now, "updated_at": now,
        }
        self._write(self._repo / "nodes" / f"{node_id}.json", data)
        return node_id

    def update_node(self, node_id: str, **attrs: object) -> None:
        self._require_unlocked()
        node = self.get_node(node_id)
        if node is None:
            raise RuntimeError(f"Node not found: {node_id}")
        for k, v in attrs.items():
            if k in NODE_UPDATABLE:
                node[k] = v
            elif k == "attributes":
                node["attributes_json"] = json.dumps(v)
        node["updated_at"] = _now_iso()
        self._write(self._repo / "nodes" / f"{node_id}.json", node)

    def delete_node(self, node_id: str) -> None:
        """Delete the node and everything keyed to it: its architecture bindings and its
        participation in analyses that did not author it. Leaving either behind is what left the
        shipped seed naming nodes that no longer existed."""
        self._require_unlocked()
        (self._repo / "nodes" / f"{node_id}.json").unlink(missing_ok=True)
        self._delete_arch_refs_of_node(node_id)
        self.remove_all_analysis_members_of_node(node_id)

    def _delete_arch_refs_of_node(self, node_id: str) -> None:
        for ref in self.list_arch_refs(assurance_node_id=node_id):
            filename = _ref_filename(node_id, str(ref["ref_type"]), str(ref["arch_artifact_id"]))
            (self._repo / "refs" / filename).unlink(missing_ok=True)

    # ── Edge CRUD ─────────────────────────────────────────────────────────────

    def list_edges(
        self,
        *,
        source_id: str | None = None,
        target_id: str | None = None,
        conn_type: str | None = None,
    ) -> list[dict[str, object]]:
        self._require_unlocked()
        edges: list[dict[str, object]] = []
        for path in sorted((self._repo / "edges").glob("*.json")):
            edge = json.loads(path.read_text())
            if source_id and edge.get("source_id") != source_id:
                continue
            if target_id and edge.get("target_id") != target_id:
                continue
            if conn_type and edge.get("conn_type") != conn_type:
                continue
            edges.append(edge)
        return as_edge_records(edges)

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        conn_type: str,
        *,
        attributes: dict[str, object] | None = None,
    ) -> str:
        self._require_unlocked()
        edge_id = make_edge_id(source_id, target_id, conn_type)
        data: dict[str, object] = {
            "edge_id": edge_id, "source_id": source_id, "target_id": target_id,
            "conn_type": conn_type, "attributes_json": json.dumps(attributes or {}),
            "created_at": _now_iso(),
        }
        self._write(self._repo / "edges" / f"{edge_id}.json", data)
        return edge_id

    def remove_edge(self, edge_id: str) -> None:
        self._require_unlocked()
        (self._repo / "edges" / f"{edge_id}.json").unlink(missing_ok=True)

    # ── Architecture cross-references ──────────────────────────────────────────

    def register_arch_ref(
        self, assurance_node_id: str, arch_artifact_id: str, ref_type: str
    ) -> None:
        self._require_unlocked()
        filename = _ref_filename(assurance_node_id, ref_type, arch_artifact_id)
        path = self._repo / "refs" / filename
        if not path.exists():
            self._write(path, {
                "assurance_node_id": assurance_node_id,
                "arch_artifact_id": arch_artifact_id,
                "ref_type": ref_type,
                "resolved_at": None,
            })

    def mark_arch_ref_resolved(
        self, assurance_node_id: str, arch_artifact_id: str, ref_type: str
    ) -> None:
        self._require_unlocked()
        filename = _ref_filename(assurance_node_id, ref_type, arch_artifact_id)
        path = self._repo / "refs" / filename
        ref = self._read(path)
        if ref:
            ref["resolved_at"] = _now_iso()
            self._write(path, ref)

    def retarget_arch_refs(self, *, new_arch_artifact_id: str) -> int:
        """Rewrite refs naming this artifact under an older slug. The id is in the filename too, so
        each record moves rather than being edited in place."""
        self._require_unlocked()
        moved = 0
        for ref in refs_to_retarget(self.list_arch_refs(), new_arch_artifact_id=new_arch_artifact_id):
            node_id, ref_type = str(ref["assurance_node_id"]), str(ref["ref_type"])
            old_path = self._repo / "refs" / _ref_filename(node_id, ref_type, str(ref["arch_artifact_id"]))
            new_path = self._repo / "refs" / _ref_filename(node_id, ref_type, new_arch_artifact_id)
            self._write(new_path, {**ref, "arch_artifact_id": new_arch_artifact_id})
            if new_path != old_path:
                old_path.unlink(missing_ok=True)
            moved += 1
        return moved

    def list_arch_refs(
        self,
        *,
        assurance_node_id: str | None = None,
        arch_artifact_id: str | None = None,
    ) -> list[dict[str, object]]:
        self._require_unlocked()
        refs: list[dict[str, object]] = []
        for path in sorted((self._repo / "refs").glob("*.json")):
            ref = json.loads(path.read_text())
            if assurance_node_id and ref.get("assurance_node_id") != assurance_node_id:
                continue
            if arch_artifact_id and ref.get("arch_artifact_id") != arch_artifact_id:
                continue
            refs.append(ref)
        return as_arch_ref_records(refs)

    def search_nodes(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        """Matching and ranking are the domain's rule, not this store's — see `node_search`.

        This used to be a local substring filter, identical in three stores and *less* capable than the
        SQLCipher store's SQL, which ranks a name match above a body match. Sharing the rule is what
        makes the four backends answer the same question.
        """
        return rank_node_matches(self.list_nodes(), query, limit=limit)

    # ── Stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> dict[str, object]:
        self._require_unlocked()
        nodes_dir = self._repo / "nodes"
        edges_dir = self._repo / "edges"
        return {
            "node_count": len(list(nodes_dir.glob("*.json"))),
            "edge_count": len(list(edges_dir.glob("*.json"))),
            "by_type": {},
        }

"""Encrypted private-git-backed confidential assurance store adapter (SC-3).

Extends PrivateGitAssuranceStore with at-rest encryption using Fernet
(AES-128-CBC + HMAC-SHA256, from the `cryptography` package). Each JSON file
is encrypted before being written; the in-memory read model is queryable after
decrypt-on-load.

Key management reuses the OS keychain under the same service name as the
SQLCipher store, with a distinct account ("private-git-encryption-key").
Recovery key export via arch-assurance export-key also covers this key.

No plaintext appears in git history when encrypt=True; existing commits have
no plaintext to migrate (pre-release, .arch-assurance-git/ absent).
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from src.application.assurance_node_sorting import sorted_node_dicts
from src.domain.assurance.assurance_node_types import NODE_UPDATABLE
from src.domain.clock import utc_now_iso as _now_iso
from src.infrastructure.assurance._analysis_records import ANALYSES_DIR, FileAnalysisStoreMixin
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

if TYPE_CHECKING:
    from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

_LOCKED_MSG = "Encrypted assurance store is locked. Call unlock() first."


def _ref_filename(assurance_node_id: str, ref_type: str, arch_artifact_id: str) -> str:
    return f"{assurance_node_id}__{ref_type}__{arch_artifact_id}.enc"


class EncryptedPrivateGitAssuranceStore(
    FileAnalysisStoreMixin, FileGroupingStoreMixin, FileFmeaAssessmentMixin
):
    """ConfidentialAssuranceStore backed by a local directory tree with Fernet encryption.

    On-disk files are Fernet-encrypted JSON; git history contains only ciphertext.
    The Fernet key is stored in the OS keychain. Queryability is preserved because
    the read model is built in-memory on unlock (decrypt-on-load).
    """

    _ANALYSIS_EXT = "enc"

    # Factor records go through this store's own encrypting `_write`, so a judgement is encrypted
    # at rest by the same path as the nodes it rates.
    _ASSESSMENT_SUFFIX = ".enc"

    def __init__(self, repo_path: Path) -> None:
        self._repo = repo_path
        self._fernet: Fernet | None = None
        self._unlocked = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def is_unlocked(self) -> bool:
        return self._unlocked

    def unlock(self) -> None:
        from cryptography.fernet import Fernet  # type: ignore[import-untyped]  # noqa: PLC0415

        from src.infrastructure.assurance import _credential_accounts as accounts  # noqa: PLC0415

        raw_key = accounts.read(accounts.GIT_KEY, self._repo)
        if raw_key is None:
            raise RuntimeError(
                "Encrypted private-git store key not found in OS keychain. "
                "Run `arch-assurance init --backend private-git` to initialise."
            )
        self._fernet = Fernet(raw_key.encode())
        self._repo.mkdir(parents=True, exist_ok=True)
        for subdir in (
            "nodes", "edges", "refs", ANALYSES_DIR, GROUPS_DIR, MEMBERS_DIR,
            FMEA_ASSESSMENTS_DIR,
        ):
            (self._repo / subdir).mkdir(exist_ok=True)
        self._unlocked = True
        logger.info("Encrypted private-git store unlocked at %s", self._repo)

    def lock(self) -> None:
        self._fernet = None
        self._unlocked = False

    def _require_unlocked(self) -> None:
        if not self._unlocked or self._fernet is None:
            raise RuntimeError(_LOCKED_MSG)

    # ── Encrypted I/O ─────────────────────────────────────────────────────────

    def _write(self, path: Path, data: dict[str, object]) -> None:
        import json

        from cryptography.fernet import Fernet  # type: ignore[import-untyped]

        assert isinstance(self._fernet, Fernet)
        plaintext = json.dumps(data).encode()
        ciphertext = self._fernet.encrypt(plaintext)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(ciphertext)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except Exception:  # noqa: BLE001
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _read(self, path: Path) -> dict[str, object] | None:
        import json

        from cryptography.fernet import Fernet, InvalidToken  # type: ignore[import-untyped]

        if not path.exists():
            return None
        assert isinstance(self._fernet, Fernet)
        try:
            plaintext = self._fernet.decrypt(path.read_bytes())
            return json.loads(plaintext)  # type: ignore[return-value]
        except InvalidToken:
            logger.warning("Decrypt failed for %s — skipping (wrong key?)", path)
            return None

    def _read_all(self, directory: Path) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        for path in sorted(directory.glob("*.enc")):
            item = self._read(path)
            if item is not None:
                results.append(item)
        return results

    # ── Analysis aggregate ─ provided by FileAnalysisStoreMixin (analyses/*.enc) ──

    # ── Node CRUD ─────────────────────────────────────────────────────────────

    def get_node(self, node_id: str) -> dict[str, object] | None:
        self._require_unlocked()
        return self._read(self._repo / "nodes" / f"{node_id}.enc")

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
        results: list[dict[str, object]] = []
        for node in self._read_all(self._repo / "nodes"):
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
            results.append(node)
        return sorted_node_dicts(results, sort, order)

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
        import json

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
        self._write(self._repo / "nodes" / f"{node_id}.enc", data)
        return node_id

    def update_node(self, node_id: str, **attrs: object) -> None:
        import json

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
        self._write(self._repo / "nodes" / f"{node_id}.enc", node)

    def delete_node(self, node_id: str) -> None:
        """Delete the node and everything keyed to it: its architecture bindings and its
        participation in analyses that did not author it. Leaving either behind is what left the
        shipped seed naming nodes that no longer existed."""
        self._require_unlocked()
        (self._repo / "nodes" / f"{node_id}.enc").unlink(missing_ok=True)
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
        results: list[dict[str, object]] = []
        for edge in self._read_all(self._repo / "edges"):
            if source_id and edge.get("source_id") != source_id:
                continue
            if target_id and edge.get("target_id") != target_id:
                continue
            if conn_type and edge.get("conn_type") != conn_type:
                continue
            results.append(edge)
        return results

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        conn_type: str,
        *,
        attributes: dict[str, object] | None = None,
    ) -> str:
        import json

        self._require_unlocked()
        edge_id = make_edge_id(source_id, target_id, conn_type)
        data: dict[str, object] = {
            "edge_id": edge_id, "source_id": source_id, "target_id": target_id,
            "conn_type": conn_type, "attributes_json": json.dumps(attributes or {}),
            "created_at": _now_iso(),
        }
        self._write(self._repo / "edges" / f"{edge_id}.enc", data)
        return edge_id

    def remove_edge(self, edge_id: str) -> None:
        self._require_unlocked()
        (self._repo / "edges" / f"{edge_id}.enc").unlink(missing_ok=True)

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

    def list_arch_refs(
        self,
        *,
        assurance_node_id: str | None = None,
        arch_artifact_id: str | None = None,
    ) -> list[dict[str, object]]:
        self._require_unlocked()
        results: list[dict[str, object]] = []
        for ref in self._read_all(self._repo / "refs"):
            if assurance_node_id and ref.get("assurance_node_id") != assurance_node_id:
                continue
            if arch_artifact_id and ref.get("arch_artifact_id") != arch_artifact_id:
                continue
            results.append(ref)
        return results

    def search_nodes(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        q = query.lower()
        results: list[dict[str, object]] = []
        for node in self.list_nodes():
            if q in str(node.get("name", "")).lower() or q in str(node.get("content_text", "")).lower():
                results.append(node)
                if len(results) >= limit:
                    break
        return results

    # ── Stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> dict[str, object]:
        self._require_unlocked()
        return {
            "node_count": len(list((self._repo / "nodes").glob("*.enc"))),
            "edge_count": len(list((self._repo / "edges").glob("*.enc"))),
            "by_type": {},
        }

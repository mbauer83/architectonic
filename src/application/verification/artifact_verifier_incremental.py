import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from src.application.repo_path_helpers import all_model_roots
from src.application.verification.artifact_verifier_parsing import parse_connection_refs, parse_diagram_refs
from src.application.verification.artifact_verifier_types import (
    IncrementalState,
    VerificationResult,
    VerifierRuntimeConfig,
    entity_id_from_path,
)
from src.domain.repository.repo_layout import DIAGRAM_CATALOG, DIAGRAMS


@dataclass
class FileInventory:
    repo_path: Path
    include_diagrams: bool = True
    rel_to_path: dict[str, Path] = field(default_factory=dict)
    path_to_rel: dict[Path, str] = field(default_factory=dict)
    snapshots: dict[str, dict[str, int | str]] = field(default_factory=dict)
    ordered_paths: list[str] = field(default_factory=list)
    entity_relpaths: list[str] = field(default_factory=list)
    connection_relpaths: list[str] = field(default_factory=list)
    diagram_puml_relpaths: list[str] = field(default_factory=list)
    diagram_matrix_relpaths: list[str] = field(default_factory=list)
    file_type_by_relpath: dict[str, Literal["entity", "connection", "diagram"]] = field(default_factory=dict)
    entity_path_by_id: dict[str, str] = field(default_factory=dict)
    connection_refs_by_path: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = field(default_factory=dict)
    connection_paths_by_entity: dict[str, set[str]] = field(default_factory=dict)
    neighbor_entities: dict[str, set[str]] = field(default_factory=dict)
    diagram_paths_by_entity: dict[str, set[str]] = field(default_factory=dict)
    diagram_paths_by_connection_id: dict[str, set[str]] = field(default_factory=dict)

    def add_file(self, path: Path, file_type: Literal["entity", "connection", "diagram"]) -> str:
        rel = str(path.relative_to(self.repo_path))
        self.rel_to_path[rel] = path
        self.path_to_rel[path] = rel
        self.path_to_rel[path.resolve()] = rel
        self.snapshots[rel] = {
            "content_hash": content_hash(path),
            "file_type": file_type,
        }
        self.file_type_by_relpath[rel] = file_type
        return rel


# Bumped when the shape or meaning of the persisted state changes. The loader rejects any
# other value, so a state written by an older verifier is discarded rather than
# misinterpreted — version 1 keyed file identity on mtime+size, version 2 on content hash.
STATE_SCHEMA_VERSION = 2


def verifier_engine_signature() -> str:
    """Fingerprint the verifier's own rules, so cached results never outlive them.

    Incremental state has to be invalidated when the rules change, even though the
    repository files and git HEAD have not: otherwise an upgraded verifier keeps reporting
    what the previous one concluded, and a newly added rule stays invisible until some file
    happens to change. A silent stale pass is the worst outcome available here — it looks
    exactly like a clean repository.

    Every module in this package is hashed, rather than a hand-listed subset. A list has to
    be maintained in step with the filenames it names, and when it is not, it degrades
    silently in the unsafe direction: nothing fails, the signature simply stops responding
    to the rules it was meant to watch. Content, not mtime, so a fresh checkout of unchanged
    rules does not force a needless full pass.
    """
    return source_tree_signature(Path(__file__).parent)


def content_hash(path: Path) -> str:
    """Content fingerprint of one artifact file — the identity cache validity turns on.

    Content, not mtime+size: that keying both missed same-length edits and discarded
    still-valid caches on any metadata-only rewrite (clone, copy, checkout). Hazard
    analysis in tests/application/verification/test_incremental_cache_validity.py.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(131072), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_tree_signature(package_dir: Path) -> str:
    """Content fingerprint of every ``*.py`` directly in *package_dir*, name-ordered."""
    digest = hashlib.sha256()
    for module_path in sorted(package_dir.glob("*.py")):
        digest.update(module_path.name.encode("utf-8"))
        try:
            digest.update(hashlib.sha256(module_path.read_bytes()).digest())
        except OSError:
            # Unreadable now, readable later: mark it distinctly so the signature changes
            # deterministically once the file can be hashed.
            digest.update(b"unreadable")
    return digest.hexdigest()[:16]


def load_runtime_config() -> VerifierRuntimeConfig:
    mode_raw = os.getenv("ARCH_MODEL_VERIFY_MODE", "incremental").strip().lower()
    mode: Literal["full", "incremental"] = "incremental" if mode_raw == "incremental" else "full"

    state_root_raw = os.getenv("ARCH_MODEL_VERIFY_STATE_DIR", "").strip()
    if state_root_raw:
        state_dir = Path(state_root_raw).expanduser()
    else:
        xdg_cache = os.getenv("XDG_CACHE_HOME", "").strip()
        cache_root = Path(xdg_cache).expanduser() if xdg_cache else Path.home() / ".cache"
        state_dir = cache_root / "arch-agents" / "model-verifier"

    ratio = _read_float_env("ARCH_MODEL_VERIFY_INCREMENTAL_MAX_CHANGED_RATIO", default=0.30)
    count = _read_int_env("ARCH_MODEL_VERIFY_INCREMENTAL_MAX_CHANGED_COUNT", default=200)
    log_mode = _read_bool_env("ARCH_MODEL_VERIFY_LOG_MODE", default=True)

    return VerifierRuntimeConfig(
        mode=mode,
        state_dir=state_dir,
        changed_ratio_threshold=min(max(ratio, 0.01), 1.0),
        changed_count_threshold=max(1, count),
        log_mode=log_mode,
    )


def _read_float_env(name: str, *, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _read_int_env(name: str, *, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _read_bool_env(name: str, *, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


def inventory_files(repo_path: Path, *, include_diagrams: bool) -> FileInventory:
    inventory = _new_inventory(repo_path=repo_path, include_diagrams=include_diagrams)
    _index_entity_files(inventory)
    _index_connection_files(inventory)
    if include_diagrams:
        _index_diagram_files(inventory)
    inventory.ordered_paths = (
        inventory.entity_relpaths
        + inventory.connection_relpaths
        + inventory.diagram_puml_relpaths
        + inventory.diagram_matrix_relpaths
    )
    return inventory


def _new_inventory(repo_path: Path, *, include_diagrams: bool) -> FileInventory:
    return FileInventory(repo_path=repo_path, include_diagrams=include_diagrams)


def _index_entity_files(inventory: FileInventory) -> None:
    # Walk every model root — the legacy top-level model/ plus each projects/<slug>/model/
    # (target group-aware layout). Rooting only at model/ silently excludes all
    # project-scoped entities from verification; the index scan uses all_model_roots too.
    for entity_root in all_model_roots(inventory.repo_path):
        for path in sorted(entity_root.rglob("*.md")):
            if path.name.endswith(".outgoing.md"):
                continue
            rel = _add_indexed_file(inventory, path, "entity")
            inventory.entity_relpaths.append(rel)
            inventory.entity_path_by_id[entity_id_from_path(path)] = rel


def _index_connection_files(inventory: FileInventory) -> None:
    for model_root in all_model_roots(inventory.repo_path):
        for path in sorted(model_root.rglob("*.outgoing.md")):
            rel = _add_indexed_file(inventory, path, "connection")
            inventory.connection_relpaths.append(rel)
            refs = parse_connection_refs(path)
            if refs is None:
                continue
            source_ids = refs.source_ids
            target_ids = refs.target_ids
            inventory.connection_refs_by_path[rel] = (source_ids, target_ids)
            _index_connection_neighbors(inventory, rel, source_ids, target_ids)


def _index_connection_neighbors(
    inventory: FileInventory,
    rel: str,
    source_ids: tuple[str, ...],
    target_ids: tuple[str, ...],
) -> None:
    for source_id in source_ids:
        inventory.connection_paths_by_entity.setdefault(source_id, set()).add(rel)
        inventory.neighbor_entities.setdefault(source_id, set())
    for target_id in target_ids:
        inventory.connection_paths_by_entity.setdefault(target_id, set()).add(rel)
        inventory.neighbor_entities.setdefault(target_id, set())
    for source_id in source_ids:
        for target_id in target_ids:
            inventory.neighbor_entities.setdefault(source_id, set()).add(target_id)
            inventory.neighbor_entities.setdefault(target_id, set()).add(source_id)


def _index_diagram_files(inventory: FileInventory) -> None:
    diagrams_dir = inventory.repo_path / DIAGRAM_CATALOG / DIAGRAMS
    if not diagrams_dir.exists():
        return
    for path in sorted(diagrams_dir.rglob("*.puml")):
        rel = _add_indexed_file(inventory, path, "diagram")
        inventory.diagram_puml_relpaths.append(rel)
        _add_diagram_refs(path, rel, inventory.diagram_paths_by_entity, inventory.diagram_paths_by_connection_id)
    for path in sorted(diagrams_dir.rglob("*.md")):
        rel = _add_indexed_file(inventory, path, "diagram")
        inventory.diagram_matrix_relpaths.append(rel)
        _add_diagram_refs(path, rel, inventory.diagram_paths_by_entity, inventory.diagram_paths_by_connection_id)


def _add_indexed_file(
    inventory: FileInventory,
    path: Path,
    file_type: Literal["entity", "connection", "diagram"],
) -> str:
    return inventory.add_file(path, file_type)


def _add_diagram_refs(
    path: Path,
    rel: str,
    diagram_paths_by_entity: dict[str, set[str]],
    diagram_paths_by_connection_id: dict[str, set[str]],
) -> None:
    refs = parse_diagram_refs(path)
    if refs is None:
        return
    for eid in refs["entity_ids"]:
        diagram_paths_by_entity.setdefault(eid, set()).add(rel)
    for cid in refs["connection_ids"]:
        diagram_paths_by_connection_id.setdefault(cid, set()).add(rel)


def state_file_path(repo_path: Path, *, include_diagrams: bool, state_dir: Path) -> Path:
    key = hashlib.sha256(str(repo_path.resolve()).encode("utf-8")).hexdigest()[:16]
    suffix = "with-diagrams" if include_diagrams else "no-diagrams"
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        fallback_dir = repo_path / ".arch" / "model-verifier"
        try:
            fallback_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            fallback_dir = Path(tempfile.gettempdir()) / "arch-agents" / "model-verifier"
            fallback_dir.mkdir(parents=True, exist_ok=True)
        state_dir = fallback_dir
    return state_dir / f"{key}.{suffix}.state-v1.json"


def load_incremental_state(path: Path) -> IncrementalState | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    if int(raw.get("schema_version", -1)) != STATE_SCHEMA_VERSION:
        return None
    snapshots = raw.get("snapshots", {})
    results = raw.get("results", {})
    if not isinstance(snapshots, dict) or not isinstance(results, dict):
        return None
    git_head = raw.get("git_head")
    return IncrementalState(
        schema_version=STATE_SCHEMA_VERSION,
        engine_signature=str(raw.get("engine_signature", "")),
        include_diagrams=bool(raw.get("include_diagrams", True)),
        git_head=str(git_head) if isinstance(git_head, str) else None,
        snapshots=snapshots,
        results=results,
        include_registry=bool(raw.get("include_registry", False)),
    )


def save_incremental_state(path: Path, state: IncrementalState) -> None:
    payload = {
        "schema_version": state.schema_version,
        "engine_signature": state.engine_signature,
        "include_diagrams": state.include_diagrams,
        "include_registry": state.include_registry,
        "git_head": state.git_head,
        "snapshots": state.snapshots,
        "results": state.results,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=True), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        return


def requires_full_pass(
    prev: IncrementalState | None,
    *,
    include_diagrams: bool,
    engine_sig: str,
    has_registry: bool,
) -> bool:
    """Whether a whole cached pass must be discarded rather than reused.

    Reacts to no prior state, a different diagram scope, and a different verifier
    engine. Deliberately NOT to git HEAD; per-file staleness is detect_changed_paths.
    Both decisions are argued in
    tests/application/verification/test_incremental_cache_validity.py.
    """
    return (
        prev is None
        or prev.include_diagrams != include_diagrams
        or prev.engine_signature != engine_sig
        or prev.include_registry != has_registry
    )


def detect_changed_paths(inv: FileInventory, prev: IncrementalState) -> tuple[set[str], set[str]]:
    changed: set[str] = set()
    deleted = set(prev.snapshots.keys()) - set(inv.snapshots.keys())
    for rel, curr in inv.snapshots.items():
        prev_item = prev.snapshots.get(rel)
        if prev_item is None:
            changed.add(rel)
            continue
        if prev_item.get("content_hash") != curr.get("content_hash"):
            changed.add(rel)
    return changed, deleted


def expand_impacted_paths(inv: FileInventory, changed: set[str]) -> set[str]:
    impacted: set[str] = set(changed)
    for rel in changed:
        path = inv.rel_to_path.get(rel)
        if path is None:
            continue
        file_type = inv.file_type_by_relpath.get(rel)
        if file_type == "entity":
            _expand_for_entity(inv, impacted, entity_id_from_path(path))
        elif file_type == "connection":
            _expand_for_connection(inv, impacted, rel, path.stem)
    return impacted


def _expand_for_entity(inv: FileInventory, impacted: set[str], entity_id: str) -> None:
    impacted |= inv.connection_paths_by_entity.get(entity_id, set())
    impacted |= inv.diagram_paths_by_entity.get(entity_id, set())
    for connection_rel in inv.connection_paths_by_entity.get(entity_id, set()):
        impacted |= inv.diagram_paths_by_connection_id.get(Path(connection_rel).stem, set())
    for neighbor_entity in inv.neighbor_entities.get(entity_id, set()):
        neighbor_path = inv.entity_path_by_id.get(neighbor_entity)
        if neighbor_path:
            impacted.add(neighbor_path)


def _expand_for_connection(inv: FileInventory, impacted: set[str], rel: str, connection_id: str) -> None:
    impacted |= inv.diagram_paths_by_connection_id.get(connection_id, set())
    refs = inv.connection_refs_by_path.get(rel)
    if refs is None:
        return
    srcs, tgts = refs
    for entity_id in (*srcs, *tgts):
        entity_rel = inv.entity_path_by_id.get(entity_id)
        if entity_rel:
            impacted.add(entity_rel)
        impacted |= inv.connection_paths_by_entity.get(entity_id, set())
        impacted |= inv.diagram_paths_by_entity.get(entity_id, set())


def _serialize_issue(i) -> dict:
    d = {"severity": i.severity, "code": i.code, "message": i.message, "location": i.location}
    if i.details is not None:
        d["details"] = dict(i.details)
    if i.actions is not None:
        d["actions"] = [dict(a) for a in i.actions]
    return d


def serialize_result(result: VerificationResult) -> dict:
    return {
        "file_type": result.file_type,
        "issues": [_serialize_issue(i) for i in result.issues],
    }


def git_head(repo_path: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    head = proc.stdout.strip()
    return head or None

import hashlib
import json
import os
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Literal

from src.application.verification._verifier_inventory import FileInventory
from src.application.verification.artifact_verifier_syntax import find_plantuml_jar
from src.application.verification.artifact_verifier_types import (
    IncrementalState,
    VerificationResult,
    VerifierRuntimeConfig,
)

#: Bumped when the stored shape changes; a mismatch discards the cache rather than misreading it.
STATE_SCHEMA_VERSION = 2


#: The product's own source tree: `src/`, three levels above this module.
PRODUCT_SOURCE = Path(__file__).resolve().parents[2]

#: Directories holding nothing a verdict is computed from: the interpreter's own caches.
_NOT_SOURCE = frozenset({"__pycache__"})


@lru_cache(maxsize=1)
def verifier_engine_signature() -> str:
    """Fingerprint everything a verdict is computed from, so cached results never outlive it.

    Incremental state has to be invalidated when the rules change, even though the
    repository files and git HEAD have not: otherwise an upgraded verifier keeps reporting
    what the previous one concluded, and a newly added rule stays invisible until some file
    happens to change. A silent stale pass is the worst outcome available here — it looks
    exactly like a clean repository.

    **The whole product source, and the renderer.** This hashed the verification package alone,
    which is where the rules are *dispatched* and not where they are decided: a rule here asks the
    domain what a relationship may join, a diagram type what its own statements mean, an ontology's
    YAML which types exist, and — through adapters it is handed at composition, so no import shows
    it — the reader of a rendered picture. A corrected rule in any of those went on being reported
    from the cache as it was before the correction. A list of the packages that matter has to be
    kept in step with what the rules reach, and degrades silently in the unsafe direction when it
    is not; the import graph does not show what is injected or loaded as data. So nothing is
    listed: every file under `src/` is hashed, with the PlantUML jar, whose drawing the syntax and
    picture findings are read from. The cost of covering more than a verdict strictly needs is one
    full pass after an upgrade, which is seconds.

    Content, not mtime, so a fresh checkout of unchanged source does not force a needless full
    pass. Computed once per process: a running process verifies with the source it loaded.
    """
    digest = hashlib.sha256(source_tree_signature(PRODUCT_SOURCE).encode("ascii"))
    digest.update(_file_digest(find_plantuml_jar()))
    return digest.hexdigest()[:16]


def engine_source_files(root: Path) -> list[Path]:
    """Every file under *root* the signature covers, in a stable order."""
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and not _NOT_SOURCE.intersection(path.relative_to(root).parts)
    )


def _file_digest(path: Path | None) -> bytes:
    if path is None:
        return b"absent"
    try:
        return hashlib.sha256(path.read_bytes()).digest()
    except OSError:
        # Unreadable now, readable later: mark it distinctly so the signature changes
        # deterministically once the file can be hashed.
        return b"unreadable"


def source_tree_signature(root: Path) -> str:
    """Content fingerprint of every file under *root*, by its path within it."""
    digest = hashlib.sha256()
    for path in engine_source_files(root):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(_file_digest(path))
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
    return full_pass_reason(
        prev, include_diagrams=include_diagrams, engine_sig=engine_sig, has_registry=has_registry
    ) is not None


def full_pass_reason(
    prev: IncrementalState | None,
    *,
    include_diagrams: bool,
    engine_sig: str,
    has_registry: bool,
) -> str | None:
    """Why a cached pass must be discarded, or None when it can be reused.

    The same four conditions ``requires_full_pass`` answers as a boolean, said out loud. A caller
    about to be told "this takes minutes" can only decide well if it is also told which applies:
    "no prior state" is a first run, while "the verifier engine changed" is what every upgrade
    produces and what an operator meets after each release.
    """
    if prev is None:
        return "no prior verification state for this repository"
    if prev.include_diagrams != include_diagrams:
        return "the diagram scope changed since the stored pass"
    if prev.engine_signature != engine_sig:
        return "the verifier engine changed since the stored pass"
    if prev.include_registry != has_registry:
        return "registry availability changed since the stored pass"
    return None


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

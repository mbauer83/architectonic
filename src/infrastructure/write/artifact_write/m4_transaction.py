from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from src.infrastructure.mutation_adapters import run_git

ChangeKind = Literal["create", "replace", "delete"]
_SHA256_LENGTH = 64


class TransactionRecoveryError(RuntimeError):
    """A durable transaction cannot be replayed without risking data loss."""


@dataclass(frozen=True)
class ManifestEntry:
    kind: ChangeKind
    dest: str
    target_hash: str
    prior_hash_or_absent: str
    payload: str | None


@dataclass(frozen=True)
class GitRefTransition:
    branch: str
    old_sha: str
    new_sha: str


@dataclass(frozen=True)
class TransactionManifest:
    entries: list[ManifestEntry]
    ref: GitRefTransition | None = None
    version: int = 1

    def to_json(self) -> bytes:
        return (json.dumps(asdict(self), indent=2, sort_keys=True) + "\n").encode()

    @classmethod
    def from_json(cls, raw: bytes) -> TransactionManifest:
        try:
            data = json.loads(raw)
            if data.get("version") != 1 or not isinstance(data.get("entries"), list):
                raise ValueError("unsupported transaction manifest")
            entries = [ManifestEntry(**entry) for entry in data["entries"]]
            ref_data = data.get("ref")
            ref = GitRefTransition(**ref_data) if ref_data is not None else None
            manifest = cls(entries=entries, ref=ref)
            _validate_manifest(manifest)
            return manifest
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise TransactionRecoveryError(f"Malformed transaction intent: {exc}") from exc


def write_transaction_intent(
    *,
    repo_root: Path,
    transaction_dir: Path,
    staged_root: Path,
    manifest: TransactionManifest,
    on_boundary: Callable[[str], None] | None = None,
) -> None:
    _validate_manifest(manifest)
    payload_root = transaction_dir / "payloads"
    payload_root.mkdir(exist_ok=True)
    fsync_directory(transaction_dir)
    for entry in manifest.entries:
        if entry.payload is None:
            continue
        source = staged_root / entry.dest
        payload = transaction_dir / _relative_path(entry.payload, field="payload")
        payload.parent.mkdir(parents=True, exist_ok=True)
        _copy_fsync(source, payload)
        if hash_file(payload) != entry.target_hash:
            raise TransactionRecoveryError(f"Payload hash mismatch for {entry.dest}")
    fsync_directory(payload_root)
    _boundary(on_boundary, "payloads_written")

    intent_tmp = transaction_dir / "intent.tmp"
    _write_fsync(intent_tmp, manifest.to_json())
    os.replace(intent_tmp, transaction_dir / "intent")
    fsync_directory(transaction_dir)
    _boundary(on_boundary, "intent_installed")


def publish_transaction(
    *,
    repo_root: Path,
    transaction_dir: Path,
    manifest: TransactionManifest,
    rebuild_index: Callable[[], object],
    on_boundary: Callable[[str], None] | None = None,
) -> None:
    _verify_payloads(transaction_dir, manifest)
    for index, entry in enumerate(manifest.entries):
        _apply_entry(repo_root, transaction_dir, entry)
        _boundary(on_boundary, f"entry_applied:{index}")
    if manifest.ref is not None:
        _apply_ref(repo_root, manifest.ref)
        _boundary(on_boundary, "ref_updated")

    _write_fsync(transaction_dir / "done", b"done\n")
    fsync_directory(transaction_dir)
    _boundary(on_boundary, "done_written")
    rebuild_index()
    _boundary(on_boundary, "index_rebuilt")
    shutil.rmtree(transaction_dir)
    fsync_directory(transaction_dir.parent)
    _boundary(on_boundary, "cleaned")


def recover_transactions(
    repo_root: Path,
    *,
    rebuild_index: Callable[[], object],
) -> int:
    transactions = repo_root / ".arch-repo" / "transactions"
    if not transactions.exists():
        return 0
    recovered = 0
    for transaction_dir in sorted(path for path in transactions.iterdir() if path.is_dir()):
        intent = transaction_dir / "intent"
        done = transaction_dir / "done"
        if not intent.exists():
            if done.exists():
                raise TransactionRecoveryError(f"Transaction {transaction_dir.name} has done without intent")
            shutil.rmtree(transaction_dir)
            fsync_directory(transactions)
            continue
        manifest = TransactionManifest.from_json(intent.read_bytes())
        if not done.exists():
            _verify_payloads(transaction_dir, manifest)
            for entry in manifest.entries:
                _apply_entry(repo_root, transaction_dir, entry)
            if manifest.ref is not None:
                _apply_ref(repo_root, manifest.ref)
            _write_fsync(done, b"done\n")
            fsync_directory(transaction_dir)
        elif done.read_bytes() != b"done\n":
            raise TransactionRecoveryError(f"Malformed done marker in {transaction_dir.name}")
        elif manifest.ref is not None:
            current = _git_output(repo_root, "rev-parse", "--verify", f"refs/heads/{manifest.ref.branch}")
            if current != manifest.ref.new_sha:
                raise TransactionRecoveryError(
                    f"Completed transaction has unexpected ref sha for {manifest.ref.branch}: {current}"
                )
        rebuild_index()
        shutil.rmtree(transaction_dir)
        fsync_directory(transactions)
        recovered += 1
    return recovered


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fsync_directory(path: Path) -> None:
    if not path.exists():
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def ensure_transactions_root(repo_root: Path) -> Path:
    """Return ``<repo>/.arch-repo/transactions``, creating it if absent and recording a
    tracked ``.arch-repo/.gitignore`` that excludes it.

    The transient transaction journal must never be staged by any commit path — normal
    ``git add .`` saves, git-sync, or ``arch-repair`` — regardless of whether the repo carries
    a top-level .gitignore.  Keeping the ignore in ``.arch-repo/.gitignore`` (not inside
    ``transactions/``) leaves the journal directory itself empty at rest.
    """
    arch_repo = repo_root / ".arch-repo"
    transactions = arch_repo / "transactions"
    transactions.mkdir(parents=True, exist_ok=True)
    gitignore = arch_repo / ".gitignore"
    lines = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    if "transactions/" not in lines:
        with gitignore.open("a", encoding="utf-8") as handle:
            handle.write("transactions/\n")
        fsync_directory(arch_repo)
    return transactions


def _apply_entry(repo_root: Path, transaction_dir: Path, entry: ManifestEntry) -> None:
    dest = _destination(repo_root, entry.dest)
    current = hash_file(dest) if dest.exists() else "absent"
    allowed = {entry.prior_hash_or_absent, entry.target_hash}
    if current not in allowed:
        raise TransactionRecoveryError(f"Third state for {entry.dest}: {current}")
    if current == entry.target_hash:
        return
    if entry.kind == "delete":
        try:
            dest.unlink()
        except FileNotFoundError:
            pass
        fsync_directory(dest.parent)
        return
    if entry.payload is None:
        raise TransactionRecoveryError(f"Missing payload declaration for {entry.dest}")
    payload = transaction_dir / _relative_path(entry.payload, field="payload")
    dest.parent.mkdir(parents=True, exist_ok=True)
    fsync_directory(dest.parent)
    _atomic_install(payload, dest)


def _atomic_install(payload: Path, dest: Path) -> None:
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{dest.name}.", dir=dest.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            with payload.open("rb") as source:
                shutil.copyfileobj(source, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, dest)
        with dest.open("rb") as handle:
            os.fsync(handle.fileno())
        fsync_directory(dest.parent)
    finally:
        temp_path.unlink(missing_ok=True)


def _apply_ref(repo_root: Path, ref: GitRefTransition) -> None:
    ref_name = f"refs/heads/{ref.branch}"
    current = _git_output(repo_root, "rev-parse", "--verify", ref_name)
    if current == ref.new_sha:
        return
    if current != ref.old_sha:
        raise TransactionRecoveryError(
            f"Unexpected ref sha for {ref.branch}: expected {ref.old_sha} or {ref.new_sha}, got {current}"
        )
    result = run_git(repo_root, ["update-ref", ref_name, ref.new_sha, ref.old_sha])
    if result.returncode != 0:
        raise TransactionRecoveryError(result.stderr.strip() or f"Failed to update {ref_name}")


def _git_output(repo_root: Path, *args: str) -> str:
    result = run_git(repo_root, args)
    if result.returncode != 0:
        raise TransactionRecoveryError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def _verify_payloads(transaction_dir: Path, manifest: TransactionManifest) -> None:
    for entry in manifest.entries:
        if entry.payload is None:
            continue
        payload = transaction_dir / _relative_path(entry.payload, field="payload")
        if not payload.is_file():
            raise TransactionRecoveryError(f"Missing payload for {entry.dest}")
        if hash_file(payload) != entry.target_hash:
            raise TransactionRecoveryError(f"Payload hash mismatch for {entry.dest}")


def _validate_manifest(manifest: TransactionManifest) -> None:
    destinations: set[str] = set()
    payloads: set[str] = set()
    for entry in manifest.entries:
        if entry.kind not in {"create", "replace", "delete"}:
            raise TransactionRecoveryError(f"Invalid transaction kind: {entry.kind}")
        _destination(Path("/validation-root"), entry.dest)
        if entry.dest in destinations:
            raise TransactionRecoveryError(f"Duplicate transaction destination: {entry.dest}")
        destinations.add(entry.dest)
        if entry.kind == "create" and entry.prior_hash_or_absent != "absent":
            raise TransactionRecoveryError(f"Create has non-absent prior state: {entry.dest}")
        if entry.kind in {"replace", "delete"} and not _is_sha256(entry.prior_hash_or_absent):
            raise TransactionRecoveryError(f"Invalid prior hash: {entry.dest}")
        if entry.kind == "delete" and (entry.target_hash != "absent" or entry.payload is not None):
            raise TransactionRecoveryError(f"Invalid delete entry: {entry.dest}")
        if entry.kind != "delete":
            if not _is_sha256(entry.target_hash):
                raise TransactionRecoveryError(f"Invalid target hash: {entry.dest}")
            if entry.payload is None:
                raise TransactionRecoveryError(f"Missing payload declaration: {entry.dest}")
            _relative_path(entry.payload, field="payload")
            if entry.payload in payloads:
                raise TransactionRecoveryError(f"Duplicate transaction payload: {entry.payload}")
            payloads.add(entry.payload)
    if manifest.ref is not None:
        if not manifest.ref.branch or ".." in manifest.ref.branch or manifest.ref.branch.startswith(("-", "/")):
            raise TransactionRecoveryError(f"Unsafe branch name: {manifest.ref.branch}")
        if not manifest.ref.old_sha or not manifest.ref.new_sha:
            raise TransactionRecoveryError("Git ref transition requires old and new shas")


def _destination(repo_root: Path, relative: str) -> Path:
    return repo_root / _relative_path(relative, field="destination")


def _relative_path(relative: str, *, field: str) -> Path:
    relpath = Path(relative)
    if relpath.is_absolute() or ".." in relpath.parts or relative in {"", "."}:
        raise TransactionRecoveryError(f"Unsafe transaction {field}: {relative}")
    return relpath


def _is_sha256(value: str) -> bool:
    return len(value) == _SHA256_LENGTH and all(char in "0123456789abcdef" for char in value)


def _copy_fsync(source: Path, dest: Path) -> None:
    with source.open("rb") as input_handle, dest.open("wb") as output_handle:
        shutil.copyfileobj(input_handle, output_handle)
        output_handle.flush()
        os.fsync(output_handle.fileno())


def _write_fsync(path: Path, data: bytes) -> None:
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _boundary(callback: Callable[[str], None] | None, name: str) -> None:
    if callback is not None:
        callback(name)

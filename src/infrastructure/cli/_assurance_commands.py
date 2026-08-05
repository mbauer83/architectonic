"""Command handler implementations for the arch-assurance CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.infrastructure.assurance import _credential_accounts as accounts
from src.infrastructure.cli._config_helpers import write_storage_config


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_db_path() -> Path:
    from src.infrastructure.deployment.layout import resolve_manifest  # noqa: PLC0415

    return resolve_manifest().assurance_db_path.path


def _default_signals_for(store_backend: str) -> str:
    if store_backend == "sqlcipher":
        return "sqlcipher-colocated"
    return "sqlite"


def _print_yaml(data: object) -> None:
    import yaml  # noqa: PLC0415

    print((yaml.dump(data, default_flow_style=False, allow_unicode=True) or "").rstrip())


def cmd_init(args: argparse.Namespace) -> int:
    from src.infrastructure.assurance.lifecycle import init_store  # noqa: PLC0415

    backend = getattr(args, "backend", None) or "sqlcipher"
    signals = getattr(args, "signals", None) or "sqlcipher-colocated"
    archive = getattr(args, "archive_backend", None)
    db_path = Path(args.db_path) if args.db_path else _default_db_path()

    if backend == "private-git":
        from src.infrastructure.cli._private_git_commands import init_private_git  # noqa: PLC0415

        result = init_private_git(args, db_path)
    else:
        try:
            result = init_store(db_path, force=args.force)
        except FileExistsError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    # --force re-init: clear this store's activation gate so unlock is required again.
    if getattr(args, "force", False):
        try:
            accounts.clear(accounts.SETUP_GATE, db_path)
        except Exception:  # noqa: BLE001
            pass

    write_storage_config(backend, signals, archive)
    result["store_backend"] = backend
    result["signals_backend"] = signals
    if archive:
        result["archive_backend"] = archive
    _print_yaml(result)
    return 0


def cmd_use_backend(args: argparse.Namespace) -> int:
    backend = args.backend
    signals = getattr(args, "signals", None) or _default_signals_for(backend)
    archive = getattr(args, "archive_backend", None)
    policy = getattr(args, "activation_policy", None)
    write_storage_config(backend, signals, archive, policy)

    from src.infrastructure.mcp.assurance_mcp.context import clear_context_cache  # noqa: PLC0415

    clear_context_cache()
    suffix = f", activation: {policy}" if policy else ""
    print(
        f"Switched to {backend} (signals: {signals}{suffix}). "
        "Restart arch-backend for changes to take effect."
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from src.config.storage_settings import (  # noqa: PLC0415
        storage_assurance_max_classification,
        storage_assurance_signals_backend,
        storage_assurance_store_backend,
    )

    db_path = Path(args.db_path) if args.db_path else _default_db_path()

    try:
        from src.config.storage_settings import (  # noqa: PLC0415
            storage_assurance_activation_policy,
            storage_assurance_archive_backend,
        )

        store_backend = storage_assurance_store_backend()
        signals_backend = storage_assurance_signals_backend()
        archive_backend = storage_assurance_archive_backend()
        max_cls = storage_assurance_max_classification()
        activation_policy = storage_assurance_activation_policy()
    except ValueError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    key_present = False
    setup_confirmed = False
    try:
        key_account = accounts.GIT_KEY if store_backend == "private-git" else accounts.DB_KEY
        key_present = accounts.present(key_account, db_path)
        setup_confirmed = accounts.present(accounts.SETUP_GATE, db_path)
    except Exception:  # noqa: BLE001
        pass

    # "Unlocked" describes a process holding the store open, not the files on disk, so this
    # reports the backend that serves the capability rather than probing from the CLI's own
    # short-lived process.
    from src.infrastructure.cli._assurance_status import resolve_lock_state  # noqa: PLC0415

    unlocked, status_str, note = resolve_lock_state(
        store_backend=store_backend,
        db_path=db_path,
        key_present=key_present,
        setup_confirmed=setup_confirmed,
        workspace_root=_workspace_root(),
    )

    _print_yaml({
        "store_backend": store_backend,
        "signals_backend": signals_backend,
        "archive_backend": archive_backend,
        "max_classification": max_cls,
        "activation_policy": activation_policy,
        "db_path": str(db_path),
        "db_exists": db_path.exists(),
        "key_in_keychain": key_present,
        "setup_confirmed": setup_confirmed,
        "unlocked": unlocked,
        "status": status_str,
        "note": note,
    })
    return 0


def _notify_backend_reload(*, authorize: bool | None = None) -> None:
    """Best-effort POST to *this workspace's* backend to reload the assurance bundle.

    ``authorize`` carries the operator's intent to the running process: True where the command
    grants access, False where it revokes it, None to leave authorization untouched. Under the
    manual activation policy this is what makes the command take effect on the process that is
    already running rather than only on the next start.

    Which process that is has to be decided by what it serves. Composed from the configured port,
    this call authorized a neighbouring workspace's backend to open *its* confidential store — an
    unlock ceremony in one workspace granting access in another.
    """
    import json  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    try:
        from src.infrastructure.cli._workspace_backend import workspace_backend_url  # noqa: PLC0415

        base_url = workspace_backend_url()
        if base_url is None:
            return
        payload = json.dumps({} if authorize is None else {"authorize": authorize}).encode()
        req = urllib.request.Request(
            f"{base_url}/api/assurance/reload",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=3):
            pass
    except Exception:  # noqa: BLE001
        pass  # Backend not running — the activation policy applies at its next start.


def cmd_unlock(args: argparse.Namespace) -> int:
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore  # noqa: PLC0415

    db_path = Path(args.db_path) if args.db_path else _default_db_path()
    store = SQLCipherAssuranceStore(db_path)
    try:
        store.unlock()
        stats = store.stats()
        store.lock()
        # Record that this store was ceremonially activated at least once. Whether a future
        # process may open it unattended is a separate, deployment-level question.
        accounts.write(accounts.SETUP_GATE, db_path, "1")
        # Authorize the running backend (if any) immediately: under the manual policy a plain
        # reload would re-apply the policy and stay locked, so the command would do nothing.
        _notify_backend_reload(authorize=True)
        _print_yaml({
            "status": "unlocked_and_verified",
            "db_path": str(db_path),
            "stats": stats,
            "note": (
                "Store activated and the running backend authorized. Whether a newly started "
                "process opens the store by itself depends on "
                "storage.assurance.activation_policy: 'manual' (default) starts locked and "
                "needs this command again, 'persistent' opens from the activation gate until "
                "`arch-assurance lock`. Either way this bounds application-level access, not "
                "key extraction — the key stays in the OS keychain. "
                "Run `arch-assurance export-key` to save your recovery key offline."
            ),
        })
        return 0
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def cmd_lock(args: argparse.Namespace) -> int:
    """Revoke access: clear the activation gate and close the store in the running backend.

    The inverse of `unlock`. Revocation takes effect immediately on the running process rather
    than at its next start, or this command would report success while access stayed open. The
    encryption key stays in the OS keychain, so `unlock` re-enables access without the recovery
    key — and so this bounds application-level access, not key extraction.
    """
    db_path = Path(args.db_path) if args.db_path else _default_db_path()
    try:
        accounts.clear(accounts.SETUP_GATE, db_path)
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    _notify_backend_reload(authorize=False)
    _print_yaml({
        "status": "locked",
        "note": (
            "Access revoked, with immediate effect on a running backend. The store will not "
            "open until you run `arch-assurance unlock` again. The encryption key remains in "
            "the OS keychain, so this bounds application-level access, not key extraction."
        ),
    })
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    from src.infrastructure.assurance.lifecycle import backup_store  # noqa: PLC0415

    db_path = Path(args.db_path) if args.db_path else _default_db_path()
    backup_path = Path(args.backup_path) if args.backup_path else None
    try:
        result = backup_store(db_path, backup_path=backup_path)
        print(f"Backed up to {result['backup_path']}.")
        return 0
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def cmd_export(args: argparse.Namespace) -> int:
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore  # noqa: PLC0415
    from src.infrastructure.assurance.lifecycle import export_store  # noqa: PLC0415

    db_path = Path(args.db_path) if args.db_path else _default_db_path()
    store = SQLCipherAssuranceStore(db_path)
    try:
        store.unlock()
        result = export_store(store, Path(args.output))
        print(f"Exported {result['node_count']} nodes to {result['output_path']}.")
        return 0
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        store.lock()


def cmd_import(args: argparse.Namespace) -> int:
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore  # noqa: PLC0415
    from src.infrastructure.assurance.lifecycle import import_store  # noqa: PLC0415

    db_path = Path(args.db_path) if args.db_path else _default_db_path()
    store = SQLCipherAssuranceStore(db_path)
    try:
        store.unlock()
        result = import_store(store, Path(args.input), replace=args.replace)
        print(f"Imported {result['counts']} from {result['input_path']}.")
        return 0
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        store.lock()


def cmd_rotate_key(args: argparse.Namespace) -> int:
    from src.infrastructure.assurance.lifecycle import rotate_key  # noqa: PLC0415

    db_path = Path(args.db_path) if args.db_path else _default_db_path()
    try:
        rotate_key(db_path)
        print("Key rotated. Store re-encrypted.")
        return 0
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def cmd_export_key(args: argparse.Namespace) -> int:
    from src.infrastructure.assurance.lifecycle import export_recovery_key  # noqa: PLC0415

    db_path = Path(args.db_path) if args.db_path else _default_db_path()
    try:
        result = export_recovery_key(db_path)
        print(result["recovery_key"])
        print("STORE THIS KEY SECURELY OFFLINE.", file=sys.stderr)
        return 0
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def cmd_pocketbase_init(args: argparse.Namespace) -> int:
    from src.infrastructure.assurance.pocketbase_lifecycle import create_collections  # noqa: PLC0415

    try:
        result = create_collections(args.base_url, args.admin_token)
        _print_yaml(result)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def cmd_pocketbase_status(args: argparse.Namespace) -> int:
    from src.infrastructure.assurance.pocketbase_lifecycle import check_health  # noqa: PLC0415

    healthy = check_health(args.base_url)
    state = "healthy" if healthy else "unhealthy"
    print(f"PocketBase at {args.base_url}: {state}.")
    return 0 if healthy else 1


def cmd_export_aibom(args: argparse.Namespace) -> int:
    from src.infrastructure.cli._security_commands import cmd_export_aibom  # noqa: PLC0415

    return cmd_export_aibom(args)


def cmd_scan_ai_candidates(args: argparse.Namespace) -> int:
    from src.infrastructure.cli._security_commands import cmd_scan_ai_candidates  # noqa: PLC0415

    return cmd_scan_ai_candidates(args)


def cmd_verify(args: argparse.Namespace) -> int:
    """Backend-aware chain integrity check. No key required for private-git or cloud backends."""
    from src.config.storage_settings import (  # noqa: PLC0415
        storage_assurance_archive_backend,
        storage_assurance_store_backend,
    )

    try:
        store_backend = storage_assurance_store_backend()
        archive_backend = storage_assurance_archive_backend()
    except ValueError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    if store_backend == "private-git":
        from src.infrastructure.cli._private_git_commands import verify_private_git  # noqa: PLC0415

        return verify_private_git(args)

    if archive_backend in ("s3-worm", "azure-blob-worm"):
        from src.infrastructure.assurance.store_factory import get_assurance_bundle  # noqa: PLC0415

        db_path = Path(args.db_path) if args.db_path else None
        try:
            bundle = get_assurance_bundle(_workspace_root(), db_path=db_path)
            ok = bundle.archive.verify_chain()
            entries = bundle.archive.list_entries(limit=100_000)
            _print_yaml({"chain_valid": ok, "entry_count": len(entries), "archive_backend": archive_backend})
            return 0 if ok else 2
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    from src.infrastructure.assurance._archive import SQLCipherAssuranceArchive  # noqa: PLC0415
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore  # noqa: PLC0415

    db_path = Path(args.db_path) if args.db_path else _default_db_path()
    store = SQLCipherAssuranceStore(db_path)
    try:
        store.unlock()
        archive = SQLCipherAssuranceArchive(store._thread_conn_or_none)  # noqa: SLF001
        ok = archive.verify_chain()
        entries = archive.list_entries(limit=100_000)
        _print_yaml({"chain_valid": ok, "entry_count": len(entries), "db_path": str(db_path)})
        return 0 if ok else 2
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        store.lock()


def cmd_verify_chain(args: argparse.Namespace) -> int:
    from src.infrastructure.assurance._archive import SQLCipherAssuranceArchive  # noqa: PLC0415
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore  # noqa: PLC0415

    db_path = Path(args.db_path) if args.db_path else _default_db_path()
    store = SQLCipherAssuranceStore(db_path)
    try:
        store.unlock()
        archive = SQLCipherAssuranceArchive(store._thread_conn_or_none)  # noqa: SLF001
        ok = archive.verify_chain()
        _print_yaml({"chain_valid": ok, "db_path": str(db_path)})
        return 0 if ok else 2
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        store.lock()

"""arch-assurance CLI — confidential assurance store lifecycle management.

Commands:
  init                  Initialise a new encrypted assurance store
  status                Show store configuration, backends, and lock status
  use-backend           Switch the active storage backend in config (writes settings.yaml)
  unlock                Verify the encryption key works and report store stats
  backup                Copy the encrypted DB to a timestamped backup file
  export                Export all assurance data to a JSON file (plaintext)
  import                Restore a JSON bundle into the store (inverse of export)
  seed                  Load a demo/bootstrap bundle, optionally with live signals
  rotate-key            Generate new encryption key and re-encrypt the store
  export-key            Print recovery key from the OS keychain
  verify                Backend-aware chain integrity check (private-git: no key required)
  verify-chain          Verify the audit log hash chain integrity (sqlcipher only)
  pocketbase-init       Initialise PocketBase collections
  pocketbase-status     Check PocketBase health
  export-aibom          Emit a CycloneDX 1.6 AI-BOM from provided components JSON
  scan-ai-candidates    Heuristic scan of architecture entities for AI-BOM relevance
"""

from __future__ import annotations

import argparse
import sys

from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.cli._assurance_commands import (
    cmd_backup,
    cmd_export,
    cmd_export_aibom,
    cmd_export_key,
    cmd_import,
    cmd_init,
    cmd_lock,
    cmd_pocketbase_init,
    cmd_pocketbase_status,
    cmd_rotate_key,
    cmd_scan_ai_candidates,
    cmd_status,
    cmd_unlock,
    cmd_use_backend,
    cmd_verify,
    cmd_verify_chain,
)
from src.infrastructure.cli._seed_commands import DEFAULT_SEED_FILENAME, SEED_REPO_SUBDIR, cmd_seed


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="arch-assurance",
        description="Manage the confidential assurance store lifecycle.",
    )
    parser.add_argument("--db-path", metavar="PATH", help="Override default DB path")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialise a new encrypted assurance store")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing store")
    p_init.add_argument(
        "--backend", metavar="BACKEND",
        choices=["sqlcipher", "pocketbase", "private-git"], default="sqlcipher",
        help="Store backend (default: sqlcipher)",
    )
    p_init.add_argument(
        "--signals", metavar="SIGNALS",
        choices=["sqlcipher-colocated", "sqlite", "encrypted"], default=None,
        help="Signals backend (default: sqlcipher-colocated for sqlcipher, sqlite otherwise)",
    )
    p_init.add_argument(
        "--archive-backend", metavar="ARCHIVE", dest="archive_backend",
        choices=["standard", "worm", "s3-worm", "azure-blob-worm"], default=None,
        help="Archive backend: standard (default), worm (sqlcipher), s3-worm, azure-blob-worm",
    )

    p_use_backend = sub.add_parser("use-backend", help="Switch the active storage backend in config/settings.yaml")
    p_use_backend.add_argument(
        "backend", choices=["sqlcipher", "pocketbase", "private-git"],
        help="Store backend to activate",
    )
    p_use_backend.add_argument(
        "--signals", metavar="SIGNALS",
        choices=["sqlcipher-colocated", "sqlite", "encrypted"], default=None,
        help="Signals backend to activate (default: auto-selected for backend)",
    )
    p_use_backend.add_argument(
        "--archive-backend", metavar="ARCHIVE", dest="archive_backend",
        choices=["standard", "worm", "s3-worm", "azure-blob-worm"], default=None,
        help="Archive backend: standard (default), worm (sqlcipher), s3-worm, azure-blob-worm",
    )
    p_use_backend.add_argument(
        "--activation-policy", metavar="POLICY", dest="activation_policy",
        choices=["manual", "persistent"], default=None,
        help="Whether a newly started process may open the store from the activation gate: "
             "'manual' (the shipped default) starts locked and needs `unlock` in the running "
             "process; 'persistent' opens from the gate until `lock`. Unattended deployments need "
             "'persistent' \u2014 there is nobody to run `unlock` after a restart",
    )

    sub.add_parser("status", help="Show store configuration, backends, and lock status")
    sub.add_parser(
        "unlock",
        help="Activate the store: verify the key, set the activation gate, and authorize the "
        "running backend. Whether a newly started process opens the store by itself is set by "
        "storage.assurance.activation_policy",
    )
    sub.add_parser(
        "lock",
        help="Revoke access: clear the activation gate and close the store in the running "
        "backend; the key stays in the keychain so `unlock` re-enables access",
    )

    p_backup = sub.add_parser("backup", help="Backup the encrypted DB")
    p_backup.add_argument("--backup-path", metavar="PATH", help="Destination path")

    p_export = sub.add_parser("export", help="Export all data to JSON (decrypted — handle carefully)")
    p_export.add_argument("--output", required=True, metavar="PATH", help="Output JSON file path")

    p_import = sub.add_parser("import", help="Restore a JSON bundle into the store (inverse of export)")
    p_import.add_argument("input", metavar="FILE", help="Path to the exported JSON bundle")
    p_import.add_argument(
        "--replace", action="store_true",
        help="Clear existing assurance data first (idempotent re-seed) instead of merging",
    )

    p_seed = sub.add_parser(
        "seed", help="Load a demo/bootstrap assurance bundle (idempotent re-seed)")
    p_seed.add_argument(
        "--input", metavar="PATH",
        help=f"Seed bundle (default: the active engagement repository's "
             f"{SEED_REPO_SUBDIR}/{DEFAULT_SEED_FILENAME})")
    p_seed.add_argument(
        "--with-signals", action="store_true", dest="with_signals",
        help="Also ingest live security signals for the anchors the bundle declares "
             "in its 'signal_anchors' list (generates SBOMs and queries OSV)")
    p_seed.add_argument(
        "--keep-existing", action="store_true", dest="keep_existing",
        help="Merge into existing assurance data instead of replacing it")
    p_seed.add_argument("--osv-base-url", dest="osv_base_url", default=None)

    sub.add_parser("rotate-key", help="Generate new encryption key and re-encrypt the store")
    sub.add_parser("export-key", help="Print recovery key from the OS keychain")
    sub.add_parser("verify", help="Backend-aware chain integrity check (private-git: no key required)")
    sub.add_parser("verify-chain", help="Verify the audit log hash chain integrity (sqlcipher only)")

    p_pb_init = sub.add_parser("pocketbase-init", help="Initialise PocketBase collections for assurance")
    p_pb_init.add_argument("--base-url", required=True, metavar="URL", help="PocketBase base URL")
    p_pb_init.add_argument("--admin-token", required=True, metavar="TOKEN", help="PocketBase admin Bearer token")

    p_pb_status = sub.add_parser("pocketbase-status", help="Check PocketBase health")
    p_pb_status.add_argument("--base-url", required=True, metavar="URL", help="PocketBase base URL")

    p_export_aibom = sub.add_parser("export-aibom", help="Emit a CycloneDX 1.6 AI-BOM")
    p_export_aibom.add_argument("--components-file", metavar="PATH", help="JSON file with AI-component dicts")
    p_export_aibom.add_argument("--output", metavar="PATH", help="Output file (default: stdout)")

    p_scan = sub.add_parser("scan-ai-candidates", help="Heuristic AI-BOM candidate scan")
    p_scan.add_argument("--entities-file", metavar="PATH", help="JSON file with architecture entity dicts")

    args = parser.parse_args()
    process_runtime_catalogs()
    dispatch = {
        "init": cmd_init, "status": cmd_status, "use-backend": cmd_use_backend,
        "unlock": cmd_unlock, "lock": cmd_lock, "backup": cmd_backup, "export": cmd_export,
        "import": cmd_import, "seed": cmd_seed,
        "rotate-key": cmd_rotate_key, "export-key": cmd_export_key,
        "verify": cmd_verify, "verify-chain": cmd_verify_chain,
        "pocketbase-init": cmd_pocketbase_init, "pocketbase-status": cmd_pocketbase_status,
        "export-aibom": cmd_export_aibom,
        "scan-ai-candidates": cmd_scan_ai_candidates,
    }
    sys.exit(dispatch[args.command](args))


if __name__ == "__main__":
    main()

"""Private-git backend helpers for arch-assurance CLI.

Extracted from _assurance_commands.py to keep that file within the LoC limit.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[3]


def init_private_git(args: argparse.Namespace, db_path: Path) -> dict:
    import secrets  # noqa: PLC0415

    from cryptography.fernet import Fernet  # type: ignore[import-untyped]  # noqa: PLC0415

    from src.infrastructure.assurance import _credential_accounts as accounts  # noqa: PLC0415

    repo_path = db_path.parent.parent / ".arch-assurance-git"
    if repo_path.exists() and not getattr(args, "force", False):
        print(f"Error: Private-git store already exists at {repo_path}. Use --force.", file=sys.stderr)
        sys.exit(1)
    for subdir in ("nodes", "edges", "refs"):
        (repo_path / subdir).mkdir(parents=True, exist_ok=True)
    (repo_path / "log").mkdir(parents=True, exist_ok=True)
    (repo_path / "log" / "baselines").mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key().decode()
    recovery_key = secrets.token_hex(32)
    accounts.write(accounts.GIT_KEY, repo_path, key)
    accounts.write(accounts.GIT_RECOVERY_KEY, repo_path, recovery_key)
    return {
        "status": "initialised",
        "repo_path": str(repo_path),
        "note": (
            "Encrypted private-git store ready. "
            "Run `arch-assurance unlock` to activate, "
            "then `arch-assurance export-key` to save your recovery key offline."
        ),
    }


def verify_private_git(_args: argparse.Namespace) -> int:
    from src.infrastructure.cli._assurance_commands import _print_yaml  # noqa: PLC0415

    repo_path = _workspace_root() / ".arch-assurance-git"
    chain_path = repo_path / "log" / "chain.jsonl"
    if not chain_path.exists():
        _print_yaml({"chain_valid": True, "entry_count": 0, "backend": "private-git",
                     "note": "No chain.jsonl found — log is empty."})
        return 0
    lines = [json.loads(r) for raw in chain_path.read_text(encoding="utf-8").splitlines() if (r := raw.strip())]
    prev_hash = ""
    ok = True
    for row in lines:
        row_ok = bool(row.get("entry_hash")) and str(row.get("prev_hash", "")) == prev_hash
        print(f"  seq={row.get('seq')}: {'OK' if row_ok else 'FAIL'}")
        if not row_ok:
            ok = False
        prev_hash = str(row.get("entry_hash", ""))
    _print_yaml({"chain_valid": ok, "entry_count": len(lines), "backend": "private-git"})
    return 0 if ok else 2

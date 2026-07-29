"""JSON-file-backed ``ExchangeIdentityStore`` (D10, parent plan §4.5, WU-F3a): one
``exchange_id -> artifact_id`` map per repo root, at ``.arch-repo/exchange-identity.json``.
Gitignored, following the ``.arch-repo/transactions`` precedent
(``m4_transaction.ensure_transactions_root``): this is a local operational cache re-derived
by re-importing, not a repository artifact.
"""

from __future__ import annotations

import json
from pathlib import Path

_FILENAME = "exchange-identity.json"


def _ensure_gitignored(arch_repo: Path) -> None:
    gitignore = arch_repo / ".gitignore"
    lines = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    if _FILENAME not in lines:
        with gitignore.open("a", encoding="utf-8") as handle:
            handle.write(f"{_FILENAME}\n")


class RepoExchangeIdentityStore:
    def __init__(self, repo_root: Path) -> None:
        self._path = repo_root / ".arch-repo" / _FILENAME

    def _load(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def artifact_id_for(self, exchange_id: str) -> str | None:
        return self._load().get(exchange_id)

    def record(self, exchange_id: str, artifact_id: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        mapping = self._load()
        mapping[exchange_id] = artifact_id
        self._path.write_text(json.dumps(mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _ensure_gitignored(self._path.parent)

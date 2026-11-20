"""JSON-file-backed ``ExchangeIdentityStore`` (D10, parent plan §4.5, WU-F3a): one
``exchange_id -> artifact_id`` map per repo root, at ``.arch-repo/exchange-identity.json``.
Declared runtime state (``repo_layout.RUNTIME_STATE_GLOBS``), so no commit path stages it: this is
a local operational cache re-derived by re-importing, not a repository artifact.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.domain.repository.repo_layout import ARCH_REPO, EXCHANGE_IDENTITY
from src.infrastructure.runtime_state_ignore import ensure_runtime_state_ignored


class RepoExchangeIdentityStore:
    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._path = repo_root / ARCH_REPO / EXCHANGE_IDENTITY

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
        ensure_runtime_state_ignored(self._repo_root)

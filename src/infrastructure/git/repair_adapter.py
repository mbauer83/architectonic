from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from src.config.git_identity import load_service_git_identity
from src.domain.repository.git_repair import RepairState
from src.infrastructure.mutation_adapters import run_git

_STATE_FILE = Path(".git") / "arch-repair-state.json"


class GitRepairAdapter:
    def __init__(self, repo: Path, env: dict[str, str]) -> None:
        if not (repo / ".git").is_dir():
            raise ValueError(f"Not a git repository: {repo}")
        self._repo = repo
        self._env = env

    def load_or_initialize(self, repair_branch: str) -> RepairState:
        path = self._repo / _STATE_FILE
        if path.exists():
            return RepairState(**json.loads(path.read_text(encoding="utf-8")))
        original = self._output(["rev-parse", "--abbrev-ref", "HEAD"])
        if not original or original == "HEAD" or original.startswith("repair/"):
            raise RuntimeError(f"Unsafe original branch: {original or '<none>'}")
        state = RepairState(original, repair_branch, "initialized")
        self.save(state)
        return state

    def require_expected_upstream(self, state: RepairState) -> None:
        expected = f"origin/{state.original_branch}"
        actual = self._output(
            [
                "rev-parse",
                "--abbrev-ref",
                "--symbolic-full-name",
                f"{state.original_branch}@{{upstream}}",
            ]
        )
        if actual != expected:
            raise RuntimeError(
                f"Unexpected upstream for {state.original_branch}: "
                f"{actual or '<none>'} != {expected}"
            )

    def fetch_original(self, state: RepairState) -> None:
        self._checked(["fetch", "origin", state.original_branch])

    def prepare_repair_branch(self, state: RepairState) -> None:
        exists = self._quiet(
            ["show-ref", "--verify", "--quiet", f"refs/heads/{state.repair_branch}"]
        )
        args = (
            ["switch", state.repair_branch]
            if exists
            else ["switch", "-c", state.repair_branch, state.original_branch]
        )
        self._checked(args)

    def stage_and_validate(self) -> None:
        # Stage the working tree, but NEVER the transient M4 transaction journal
        # (.arch-repo/transactions/): an interrupted write may have left one on disk, and a
        # blind `git add -A` would otherwise commit and push runtime internals. The pathspec
        # exclude holds even when the repo has no .gitignore.
        #
        # We deliberately do NOT run `git diff --cached --check`: it false-fails on legitimate
        # model content — trailing whitespace in Markdown, and `===`/`---` setext underlines it
        # mistakes for conflict markers — which is style, not correctness. Commit-worthiness is
        # decided by has_staged_changes(); referential safety by the upstream guard + ff-only
        # promote, neither of which can introduce conflict markers.
        self._checked(["add", "-A", "--", ".", ":(exclude).arch-repo/transactions"])

    def has_staged_changes(self) -> bool:
        return not self._quiet(["diff", "--cached", "--quiet"])

    def commit(self, message: str) -> None:
        identity = load_service_git_identity()
        self._checked(
            [
                "-c",
                f"user.name={identity.name}",
                "-c",
                f"user.email={identity.email}",
                "commit",
                "-m",
                message,
            ]
        )

    def push_repair(self, state: RepairState) -> None:
        self._checked(["push", "-u", "origin", state.repair_branch])

    def promote_to_original(self, state: RepairState) -> None:
        self._checked(["fetch", "origin", state.original_branch])
        self._checked(["switch", state.original_branch])
        self._checked(["merge", "--ff-only", state.repair_branch])
        self._checked(["push", "origin", state.original_branch])

    def require_clean(self) -> None:
        if self._output(["status", "--porcelain"]):
            raise RuntimeError("Repair completed with a dirty working tree")

    def save(self, state: RepairState) -> None:
        path = self._repo / _STATE_FILE
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(asdict(state), sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temp, path)

    def _checked(self, args: Sequence[str]) -> str:
        result = run_git(self._repo, args, timeout=120, env=self._env)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
        return result.stdout.strip()

    def _output(self, args: Sequence[str]) -> str:
        return self._checked(args)

    def _quiet(self, args: Sequence[str]) -> bool:
        return run_git(self._repo, args, timeout=120, env=self._env).returncode == 0

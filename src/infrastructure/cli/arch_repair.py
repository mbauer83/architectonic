from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from src.application.git_repair import execute_git_repair
from src.domain.repository.git_repair import RepairState
from src.infrastructure.git.git_auth import (
    GitCredentials,
    build_git_env,
    collect_credentials,
    create_askpass_script,
    register_token_file,
)
from src.infrastructure.git.repair_adapter import GitRepairAdapter

_SUBCOMMANDS = ("upgrade", "git-repair")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    subcommand, rest = _split_subcommand(argv)
    if subcommand == "upgrade":
        from src.infrastructure.cli.arch_repair_upgrade import main_upgrade  # noqa: PLC0415

        return main_upgrade(rest)
    return _main_git_repair(rest)


def _split_subcommand(argv: list[str]) -> tuple[str, list[str]]:
    """The legacy no-subcommand invocation is a deprecated alias for `git-repair`, kept for
    one release; any other first token that isn't a known subcommand is passed through to
    `git-repair`'s own parser so its usual arg-parsing errors still fire."""
    if argv and argv[0] in _SUBCOMMANDS:
        return argv[0], argv[1:]
    if argv and argv[0] in ("-h", "--help"):
        print(
            "usage: arch-repair {upgrade,git-repair} ...\n\n"
            "Guarded repository maintenance: git repair and format-version upgrades.\n"
            "Run `arch-repair upgrade -h` or `arch-repair git-repair -h` for subcommand options."
        )
        raise SystemExit(0)
    print(
        "arch-repair: DEPRECATED — invoking without a subcommand is a deprecated alias for "
        "'git-repair' and will be removed in a future release; use `arch-repair git-repair ...`.",
        file=sys.stderr,
    )
    return "git-repair", argv


def _main_git_repair(argv: list[str]) -> int:
    parser = _git_repair_parser()
    args = parser.parse_args(argv)
    try:
        execute_repair(
            repo=Path(args.repo_root).resolve(),
            repair_branch=args.repair_branch,
            message=args.message,
            token_file=args.git_token_file,
            confirm=args.confirm,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    return 0


def execute_repair(
    *,
    repo: Path,
    repair_branch: str,
    message: str,
    token_file: str | None = None,
    confirm: bool = False,
) -> RepairState:
    if not confirm:
        raise ValueError("Pass --confirm after reviewing the working-tree changes")
    if not repair_branch.startswith("repair/"):
        raise ValueError("repair_branch must start with 'repair/'")
    register_token_file(token_file)
    credentials = collect_credentials([repo])
    askpass = create_askpass_script()
    try:
        state = execute_git_repair(
            GitRepairAdapter(repo, _git_env(credentials, askpass)),
            repair_branch=repair_branch,
            message=message,
        )
        print(f"Repair complete: {state.repair_branch} → {state.original_branch}")
        return state
    finally:
        askpass.unlink(missing_ok=True)


def _git_repair_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arch-repair git-repair",
        description="Guarded, resumable git repair for a quiesced architecture repository.",
    )
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--repair-branch", default="repair/architecture-repair")
    parser.add_argument("--message", default="fix(model): repair architecture repository")
    parser.add_argument("--git-token-file")
    parser.add_argument("--confirm", action="store_true")
    return parser


def _git_env(credentials: GitCredentials | None, askpass: Path) -> dict[str, str]:
    if credentials is not None:
        return build_git_env(credentials, askpass)
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env

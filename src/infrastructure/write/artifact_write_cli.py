"""CLI for engagement-repository write operations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request

from src.infrastructure.cli import backend_write
from src.infrastructure.workspace.workspace_init import load_init_state


def _default_repo_root() -> Path | None:
    state = load_init_state()
    if state and "engagement_root" in state:
        return Path(state["engagement_root"])
    return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="arch-write-cli")
    parser.add_argument(
        "--repo-root",
        default=str(_default_repo_root()) if _default_repo_root() else None,
        help="Engagement repository root (default: arch-init state)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    delete_entity_parser = sub.add_parser("delete-entity", help="Delete an entity from the engagement repo")
    delete_entity_parser.add_argument("artifact_id")
    delete_entity_parser.add_argument("--dry-run", action="store_true")

    delete_diagram_parser = sub.add_parser("delete-diagram", help="Delete a diagram from the engagement repo")
    delete_diagram_parser.add_argument("artifact_id")
    delete_diagram_parser.add_argument("--dry-run", action="store_true")
    return parser


def _delete_request(base_url: str, args: argparse.Namespace) -> Request:
    """The proxied request for one delete command.

    Both surfaces carry identity in the path and the dry-run flag in the query, because a ``DELETE``
    has no body for either to travel in.
    """
    identity = quote(args.artifact_id, safe="")
    dry_run = "true" if args.dry_run else "false"
    if args.command == "delete-entity":
        return Request(
            f"{base_url}/api/entities/{identity}?dry_run={dry_run}",
            headers={"Accept": "application/json"},
            method="DELETE",
        )
    return Request(
        f"{base_url}/api/diagrams/{identity}?dry_run={dry_run}",
        headers={"Accept": "application/json"},
        method="DELETE",
    )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.repo_root:
        parser.error("No --repo-root given and no arch-init state found.")
    repo_root = Path(args.repo_root)

    try:
        base_url = backend_write.serving_url(repo_root)
        result = backend_write.send(_delete_request(base_url, args), timeout=10)
    except backend_write.BackendWriteError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if result.get("content"):
        print(str(result["content"]))
    else:
        action = "Would delete" if args.dry_run else "Deleted"
        print(f"{action} {args.command.split('-', 1)[1]} '{result.get('artifact_id')}' at {result.get('path')}")
    for warning in result.get("warnings") or []:
        print(f"Warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

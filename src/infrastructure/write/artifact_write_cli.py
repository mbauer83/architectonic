"""CLI for engagement-repository write operations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from src.infrastructure.backend.backend_probe import backend_url, probe_backend
from src.infrastructure.backend.backend_state import read_backend_state
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


def _delete_request(port: int, args: argparse.Namespace) -> Request:
    """The proxied request for one delete command.

    Both surfaces carry identity in the path and the dry-run flag in the query, because a ``DELETE``
    has no body for either to travel in.
    """
    identity = quote(args.artifact_id, safe="")
    dry_run = "true" if args.dry_run else "false"
    if args.command == "delete-entity":
        return Request(
            f"{backend_url(port)}/api/entities/{identity}?dry_run={dry_run}",
            headers={"Accept": "application/json"},
            method="DELETE",
        )
    return Request(
        f"{backend_url(port)}/api/diagrams/{identity}?dry_run={dry_run}",
        headers={"Accept": "application/json"},
        method="DELETE",
    )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.repo_root:
        parser.error("No --repo-root given and no arch-init state found.")
    repo_root = Path(args.repo_root)

    state = read_backend_state(repo_root)
    if state is None or not probe_backend(state["port"]):
        print(
            "arch-write-cli requires arch-backend to be running. "
            "Start it with: arch-backend --daemon",
            file=sys.stderr,
        )
        return 1

    req = _delete_request(state["port"], args)
    try:
        with urlopen(req, timeout=10.0) as resp:  # noqa: S310
            payload = resp.read().decode("utf-8")
            # A committed deletion answers 204 with no body; only a dry run has a plan to report.
            result: dict[str, Any] = json.loads(payload) if payload.strip() else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        print(detail or str(exc), file=sys.stderr)
        return 1
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        print(f"Backend proxy failed: {exc}", file=sys.stderr)
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

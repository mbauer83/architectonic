"""arch-icons — add a folder of icons to the repository's library.

    arch-icons import <dir> --attribution "Microsoft Azure architecture icons, used under …" \\
        --tag azure --for kubernetes-cluster [--style badge|figure] [--commit] [--repo PATH]

Every SVG, PNG, JPEG and WebP file in the folder is normalised and checked exactly as an upload through
the GUI or MCP is; nothing is written without `--commit`. The report lists what was accepted, what was
refused and why, and what the library already holds by picture. The icon's name is the file's name,
words separated.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.domain.icons.icon_ref import ICON_STYLES, IconStyle
from src.domain.icons.render_form import SourceFormat
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.artifact_index.bootstrap import notify_paths_changed
from src.infrastructure.mcp.artifact_mcp.context import default_engagement_repo_root
from src.infrastructure.verification.verifier_factory import build_artifact_verifier
from src.infrastructure.write.artifact_write.icon import IconUpload, create_icon

_FORMATS: dict[str, SourceFormat] = {".svg": "svg", ".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".webp": "webp"}


@dataclass(frozen=True, slots=True)
class ImportedFile:
    path: Path
    outcome: str  # "accepted" | "present" | "refused"
    detail: str


def run_import(
    *,
    repo_root: Path,
    folder: Path,
    attribution: str,
    tags: tuple[str, ...],
    applies_to: tuple[str, ...],
    style: IconStyle,
    commit: bool,
) -> list[ImportedFile]:
    index = shared_artifact_index([repo_root])
    catalogs = process_runtime_catalogs()
    verifier = build_artifact_verifier(ArtifactRegistry(index), catalogs=catalogs, check_puml_syntax=False)
    results: list[ImportedFile] = []
    for path in sorted(p for p in folder.iterdir() if p.suffix.lower() in _FORMATS):
        upload = IconUpload(
            content=path.read_bytes(), source_format=_FORMATS[path.suffix.lower()], name=_name_of(path),
            attribution=attribution, applies_to=applies_to, default_style=style, tags=tags,
        )
        result = create_icon(
            repo_root=repo_root, verifier=verifier, clear_repo_caches=lambda p: notify_paths_changed([p]),
            upload=upload, dry_run=not commit,
        )
        results.append(_outcome(path, result.wrote, result.artifact_id, result.verification or {}, commit))
    return results


def _name_of(path: Path) -> str:
    return " ".join(path.stem.replace("_", " ").replace("-", " ").split())


def _outcome(path: Path, wrote: bool, artifact_id: str, verification: dict, commit: bool) -> ImportedFile:
    issues = [str(issue.get("message")) for issue in verification.get("issues", []) if issue.get("severity") == "error"]
    if wrote or (not commit and not issues):
        return ImportedFile(path, "accepted", artifact_id)
    reason = "; ".join(issues) or "not written"
    return ImportedFile(path, "present" if "already holds this picture" in reason else "refused", reason)


def _print_report(results: list[ImportedFile], commit: bool) -> None:
    for outcome in ("accepted", "present", "refused"):
        chosen = [r for r in results if r.outcome == outcome]
        if chosen:
            print(f"{outcome} ({len(chosen)}):")
            for item in chosen:
                print(f"  {item.path.name}: {item.detail}")
    if not commit:
        print("Dry run: nothing was written. Re-run with --commit to add the accepted icons.")


def _cmd_import(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo).expanduser().resolve() if args.repo else default_engagement_repo_root()
    folder = Path(args.folder).expanduser()
    if not folder.is_dir():
        print(f"ERROR: {folder} is not a folder", file=sys.stderr)
        return 1
    results = run_import(
        repo_root=repo_root, folder=folder, attribution=args.attribution, tags=tuple(args.tag or ()),
        applies_to=tuple(getattr(args, "for") or ()), commit=args.commit,
        style=next(style for style in ICON_STYLES if style == args.style),
    )
    _print_report(results, args.commit)
    return 1 if any(r.outcome == "refused" for r in results) else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arch-icons", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import", help="Add every icon in a folder to the library")
    imp.add_argument("folder", metavar="DIR", help="Folder of SVG, PNG, JPEG and WebP files")
    imp.add_argument("--attribution", required=True, help="Whose marks these are, and on what terms they are used")
    imp.add_argument("--tag", action="append", metavar="TAG", help="A tag for every icon (repeatable)")
    imp.add_argument(
        "--for", action="append", metavar="NAME", help="A type or specialization they apply to (repeatable)"
    )
    imp.add_argument("--style", default="badge", choices=list(ICON_STYLES), help="Default style (default: badge)")
    imp.add_argument("--commit", action="store_true", default=False, help="Write the icons (default: dry run)")
    imp.add_argument("--repo", default=None, metavar="PATH", help="Target repo root (default: engagement repo)")
    imp.set_defaults(func=_cmd_import)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

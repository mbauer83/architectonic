"""arch-exchange: C19C v3.1 model-exchange CLI (D10, parent plan §4.5, WU-F4).

Import applies the Appendix E.4 migration table (WU-F3a); export inverts it (WU-F3b).
Both go through the ordinary ``artifact_write`` layer — the same validation the GUI/MCP
use — never raw file emission. Import is dry-run by default; pass ``--commit`` to write.

Usage:
    arch-exchange import --source <path> [--commit] [--repo <path>] [--schema <path>]
    arch-exchange export --out <path> [--scope <artifact-id> ...] [--repo <path>]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.application.exchange.export_model import ExportReport, export_model
from src.application.exchange.import_model import ImportReport, import_model
from src.application.exchange.ports import ExchangeDocumentError
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.exchange.archimate_model_exchange import (
    ArchimateModelExchangeReader,
    ArchimateModelExchangeWriter,
)
from src.infrastructure.exchange.archimate_model_exchange.concept_mapping import DeclarativeConceptMapper
from src.infrastructure.exchange.archimate_model_exchange.identity_store import RepoExchangeIdentityStore
from src.infrastructure.exchange.archimate_model_exchange.write_adapter import ArtifactWriteExchangeAdapter
from src.infrastructure.mcp.artifact_mcp.context import default_engagement_repo_root


def _resolve_repo_root(repo_arg: str | None) -> Path:
    return Path(repo_arg).expanduser().resolve() if repo_arg else default_engagement_repo_root()


def _registry(root: Path) -> ArtifactRegistry:
    return ArtifactRegistry(shared_artifact_index([root]))


def _print_import_report(report: ImportReport) -> None:
    verb = "Imported" if report.committed else "Would import (dry run)"
    print(f"{verb}: {len(report.entities)} entities, {len(report.connections)} connections")
    for entity in report.entities:
        note = f"  [{entity.warning}]" if entity.warning else ""
        print(f"  {entity.action:>7}  {entity.artifact_id}  ({entity.name}){note}")
    for connection in report.connections:
        note = f"  [{connection.warning}]" if connection.warning else ""
        print(f"  {connection.action:>7}  {connection.artifact_id}{note}")
    for item in report.unmappable:
        print(f"  UNMAPPABLE  {item.kind} {item.concept_type!r} ({item.exchange_id}): {item.reason}")
    if not report.committed:
        print("Re-run with --commit to write these changes.")


def _print_export_report(report: ExportReport, out_path: str) -> None:
    print(f"Exported {len(report.entities)} entities, {len(report.connections)} connections to {out_path}")
    for item in report.unexportable:
        label = item.artifact_id or item.archimate_type
        print(f"  UNEXPORTABLE  {item.kind} {label}: {item.reason}")


def run_import(*, repo_root: Path, source: Path, schema: Path | None, commit: bool) -> ImportReport:
    reader = ArchimateModelExchangeReader(schema_path=str(schema) if schema else None)
    document = reader.read(source.read_bytes())
    mapper = DeclarativeConceptMapper()
    registry = _registry(repo_root)
    return import_model(
        document,
        store=registry,
        identity=RepoExchangeIdentityStore(repo_root),
        mapper=mapper,
        writer=ArtifactWriteExchangeAdapter(repo_root),
        commit=commit,
    )


def run_export(*, repo_root: Path, out: Path, scope: list[str] | None) -> ExportReport:
    registry = _registry(repo_root)
    entity_ids = scope if scope else sorted(registry.entity_ids())
    report = export_model(entity_ids, entities=registry, connections=registry, mapper=DeclarativeConceptMapper())
    out.write_bytes(ArchimateModelExchangeWriter().write(report.document))
    return report


def _cmd_import(args: argparse.Namespace) -> int:
    repo_root = _resolve_repo_root(args.repo)
    try:
        report = run_import(
            repo_root=repo_root,
            source=Path(args.source),
            schema=Path(args.schema) if args.schema else None,
            commit=args.commit,
        )
    except ExchangeDocumentError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    _print_import_report(report)
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    repo_root = _resolve_repo_root(args.repo)
    report = run_export(repo_root=repo_root, out=Path(args.out), scope=args.scope)
    _print_export_report(report, args.out)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arch-exchange", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    imp = sub.add_parser("import", help="Import a C19C v3.1 model-exchange document")
    imp.add_argument("--source", required=True, metavar="PATH", help="Path to the C19C XML document")
    imp.add_argument("--commit", action="store_true", default=False, help="Write changes (default: dry run)")
    imp.add_argument("--repo", default=None, metavar="PATH", help="Target repo root (default: engagement repo)")
    imp.add_argument(
        "--schema", default=None, metavar="PATH", help="XSD schema for validation (dev/test only, never committed)"
    )
    imp.set_defaults(func=_cmd_import)

    exp = sub.add_parser("export", help="Export a C19C v3.1 model-exchange document")
    exp.add_argument("--out", required=True, metavar="PATH", help="Path to write the C19C XML document")
    exp.add_argument(
        "--scope", nargs="*", default=None, metavar="ARTIFACT_ID", help="Entity ids to export (default: every entity)"
    )
    exp.add_argument("--repo", default=None, metavar="PATH", help="Source repo root (default: engagement repo)")
    exp.set_defaults(func=_cmd_export)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

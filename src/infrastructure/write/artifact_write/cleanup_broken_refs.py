"""cleanup_broken_refs — find and remove broken global-entity-reference proxies.

A GRF becomes broken when the enterprise entity it points to no longer exists
(e.g. the entity was renamed or deleted in the enterprise repo without updating
the engagement repo).

This tool:
1. Scans all GRFs in the engagement repo
2. Checks whether each referenced enterprise entity still exists
3. For each broken GRF: removes all connections that point to it, then deletes
   the GRF file itself

dry_run=True (default) reports every removal without touching any files.

Entry points:
  - CLI:  uv run python -m src.infrastructure.write.artifact_write.cleanup_broken_refs
          [--repo-root ...] [--enterprise-root ...] [--execute]
  - REST: POST /api/cleanup-broken-refs  (GUI router, engagement only — not MCP)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from src.application.artifact_query import ArtifactRepository
from src.config.repo_paths import MODEL
from src.infrastructure.artifact_index import shared_artifact_index

_GRF_FRONTMATTER_KEY = "global-artifact-id"
_GRF_CONN_HEADER = re.compile(r"^### .+ → (.+)$", re.MULTILINE)


@dataclass
class CleanupAction:
    kind: str  # "remove_connection" | "delete_grf"
    path: str
    detail: str  # human-readable description


@dataclass
class CleanupReport:
    broken_grfs: list[str] = field(default_factory=list)
    actions: list[CleanupAction] = field(default_factory=list)
    executed: bool = False
    errors: list[str] = field(default_factory=list)


def find_broken_grfs(
    engagement_repo: ArtifactRepository,
    engagement_root: Path,
    enterprise_entity_ids: set[str],
) -> list[tuple[str, Path]]:
    """Return [(grf_artifact_id, grf_path)] for GRFs whose global-entity-id is missing."""
    broken: list[tuple[str, Path]] = []
    for rec in engagement_repo.list_entities(artifact_type="global-artifact-reference"):
        geid = rec.extra.get(_GRF_FRONTMATTER_KEY)
        if not isinstance(geid, str) or not geid:
            broken.append((rec.artifact_id, rec.path))
        elif geid not in enterprise_entity_ids:
            broken.append((rec.artifact_id, rec.path))
    return broken


def _outgoing_files_referencing(grf_id: str, model_root: Path) -> list[tuple[Path, int]]:
    """Return [(outgoing_path, count)] for files containing connections to grf_id."""
    results = []
    for f in model_root.rglob("*.outgoing.md"):
        text = f.read_text(encoding="utf-8")
        count = len(re.findall(rf"^### .+ → {re.escape(grf_id)}$", text, re.MULTILINE))
        if count:
            results.append((f, count))
    return results


def _remove_connections_to_grf(grf_id: str, outgoing_path: Path) -> str:
    """Return the outgoing file content with all connections to grf_id removed."""
    lines = outgoing_path.read_text(encoding="utf-8").splitlines(keepends=True)
    out: list[str] = []
    drop = False
    for line in lines:
        if line.startswith("### ") and " → " in line:
            tgt = line.split(" → ", 1)[1].strip()
            drop = tgt == grf_id
        elif drop and (not line.strip() or not line.startswith("### ")):
            if not line.strip():
                continue
        if not drop:
            out.append(line)
    return "".join(out)


def plan_cleanup(
    engagement_root: Path,
    enterprise_entity_ids: set[str],
) -> CleanupReport:
    """Compute what a cleanup run would do — no files are modified."""
    eng_repo = ArtifactRepository(shared_artifact_index(engagement_root))
    broken = find_broken_grfs(eng_repo, engagement_root, enterprise_entity_ids)

    report = CleanupReport(broken_grfs=[b[0] for b in broken])
    model_root = engagement_root / MODEL

    for grf_id, grf_path in broken:
        # Find outgoing files that connect to this GRF
        for out_path, count in _outgoing_files_referencing(grf_id, model_root):
            report.actions.append(
                CleanupAction(
                    kind="remove_connection",
                    path=str(out_path.relative_to(engagement_root)),
                    detail=f"Remove {count} connection(s) → {grf_id}",
                )
            )
        # Mark GRF for deletion
        report.actions.append(
            CleanupAction(
                kind="delete_grf",
                path=str(grf_path.relative_to(engagement_root)),
                detail=f"Delete broken GRF {grf_id}",
            )
        )

    return report


def execute_cleanup(
    engagement_root: Path,
    enterprise_entity_ids: set[str],
) -> CleanupReport:
    """Execute the cleanup plan — modifies files in the engagement repo."""
    report = plan_cleanup(engagement_root, enterprise_entity_ids)
    report.executed = True

    eng_repo = ArtifactRepository(shared_artifact_index(engagement_root))
    broken = find_broken_grfs(eng_repo, engagement_root, enterprise_entity_ids)
    model_root = engagement_root / MODEL

    for grf_id, grf_path in broken:
        # Remove connections first
        for out_path, _ in _outgoing_files_referencing(grf_id, model_root):
            try:
                new_content = _remove_connections_to_grf(grf_id, out_path)
                # If outgoing file becomes empty of connections, delete it
                has_connections = bool(re.search(r"^### ", new_content, re.MULTILINE))
                if has_connections:
                    out_path.write_text(new_content, encoding="utf-8")
                else:
                    out_path.unlink()
            except Exception as exc:  # noqa: BLE001
                report.errors.append(f"Error updating {out_path}: {exc}")

        # Delete GRF entity file + its outgoing if present
        try:
            grf_path.unlink(missing_ok=True)
            grf_outgoing = grf_path.with_suffix(".outgoing.md")
            grf_outgoing.unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            report.errors.append(f"Error deleting {grf_path}: {exc}")

    return report


def cleanup_broken_refs(
    engagement_root: Path,
    enterprise_root: Path,
    *,
    dry_run: bool = True,
) -> CleanupReport:
    """Top-level entry — plan or execute broken-GRF cleanup."""
    ent_repo = ArtifactRepository(shared_artifact_index(enterprise_root))
    enterprise_ids = {rec.artifact_id for rec in ent_repo.list_entities()}
    if dry_run:
        return plan_cleanup(engagement_root, enterprise_ids)
    return execute_cleanup(engagement_root, enterprise_ids)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(
        prog="arch-cleanup-broken-refs",
        description=(
            "Find and remove broken global-entity-reference proxies in an engagement repo. "
            "Default is dry-run; pass --execute to apply changes."
        ),
    )
    parser.add_argument("--repo-root", default=None, help="Engagement repo root (default: from arch-init)")
    parser.add_argument("--enterprise-root", default=None, help="Enterprise repo root (default: from arch-init)")
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Apply changes (default: dry-run only)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output JSON instead of human-readable text",
    )
    args = parser.parse_args(argv)

    from src.infrastructure.workspace.workspace_init import load_init_state

    ws = load_init_state()

    eng_root = (
        Path(args.repo_root)
        if args.repo_root
        else (Path(ws["engagement_root"]) if ws and "engagement_root" in ws else None)
    )
    ent_root = (
        Path(args.enterprise_root)
        if args.enterprise_root
        else (Path(ws["enterprise_root"]) if ws and "enterprise_root" in ws else None)
    )
    if eng_root is None or ent_root is None:
        parser.error("Could not resolve repo roots. Pass --repo-root and --enterprise-root or run arch-init.")

    report = cleanup_broken_refs(eng_root, ent_root, dry_run=not args.execute)

    if args.json:
        import dataclasses

        print(json.dumps(dataclasses.asdict(report), indent=2))
        return

    mode = "DRY RUN" if not args.execute else "EXECUTED"
    print(f"\n=== Broken-reference cleanup [{mode}] ===\n")
    if not report.broken_grfs:
        print("No broken global-entity-references found.")
        return

    print(f"Broken GRFs ({len(report.broken_grfs)}):")
    for g in report.broken_grfs:
        print(f"  • {g}")

    print(f"\nActions ({len(report.actions)}):")
    for a in report.actions:
        verb = "Would" if not args.execute else "Did"
        print(f"  [{a.kind}] {a.path}")
        print(f"          {verb}: {a.detail}")

    if report.errors:
        print(f"\nErrors ({len(report.errors)}):")
        for e in report.errors:
            print(f"  ✗ {e}")
    elif args.execute:
        print("\nCompleted successfully.")


if __name__ == "__main__":
    main()

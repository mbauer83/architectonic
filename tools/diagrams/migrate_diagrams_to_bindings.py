#!/usr/bin/env python3
"""One-time migration: convert legacy entity_id / _scope_entity_id to top-level bindings.

Scans diagram .puml files across supplied repo roots, converts any legacy inline
``entity_id`` on diagram-entities items to ``represents`` bindings, and any
``_scope_entity_id`` field inside ``diagram-entities`` to a diagram-level
``scoped-by`` binding.  Also finds and reports+deletes model connections of type
``c4-contains`` from .outgoing.md files.  Aborts (without writing) if the
post-migration verifier reports errors.

Usage:
    uv run tools/diagrams/migrate_diagrams_to_bindings.py [REPO_ROOT ...]

If no REPO_ROOT args are given, repo roots are resolved from arch-workspace.yaml.
The ENG-ARCH-REPO self-model is always included when discovered from the workspace.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml  # type: ignore[import-untyped]

# ---------------------------------------------------------------------------
# Frontmatter helpers
# ---------------------------------------------------------------------------

_FM_RE = re.compile(r"^---\n(.*?\n)---\n", re.DOTALL)


def _parse_fm(text: str) -> dict[str, object]:
    m = _FM_RE.match(text)
    if not m:
        return {}
    return yaml.safe_load(m.group(1)) or {}


def _replace_fm(text: str, fm: dict[str, object]) -> str:
    m = _FM_RE.match(text)
    body = text[m.end() :] if m else text
    yaml_text = yaml.safe_dump(fm, sort_keys=False).strip()
    return f"---\n{yaml_text}\n---\n{body}"


# ---------------------------------------------------------------------------
# Diagram migration
# ---------------------------------------------------------------------------

_SCOPE_KEY = "_scope_entity_id"


def _binding_id(element_id: str) -> str:
    return f"bind-{element_id}"


def _migrate_diagram_entities(
    diagram_entities: dict[str, object],
    existing_bindings: list[dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]], int]:
    """Return (updated_entities, new_bindings_to_add, count_added)."""
    existing_ids = {b["id"] for b in existing_bindings if isinstance(b, dict) and "id" in b}
    new_bindings: list[dict[str, object]] = []
    updated: dict[str, object] = {}
    count = 0

    for key, value in diagram_entities.items():
        if key == _SCOPE_KEY:
            scope_id = str(value).strip() if value else ""
            if scope_id:
                bid = "bind-scope"
                suffix = 0
                while bid in existing_ids or any(b["id"] == bid for b in new_bindings):
                    suffix += 1
                    bid = f"bind-scope-{suffix}"
                new_bindings.append(
                    {
                        "id": bid,
                        "subject": {"kind": "diagram"},
                        "correspondence_kind": "scoped-by",
                        "target": {"entity_id": scope_id},
                    }
                )
                count += 1
            continue  # drop _scope_entity_id from output

        if not isinstance(value, list):
            updated[key] = value
            continue

        items_out: list[object] = []
        for item in value:
            if not isinstance(item, dict):
                items_out.append(item)
                continue
            entity_id = str(item.get("entity_id", "")).strip() or None
            item_id = str(item.get("id", "")).strip()
            if entity_id and item_id:
                bid = _binding_id(item_id)
                if bid not in existing_ids and not any(b["id"] == bid for b in new_bindings):
                    new_bindings.append(
                        {
                            "id": bid,
                            "subject": {"kind": "entity", "id": item_id},
                            "correspondence_kind": "represents",
                            "target": {"entity_id": entity_id},
                        }
                    )
                    count += 1
            clean_item = {k: v for k, v in item.items() if k != "entity_id"}
            items_out.append(clean_item)
        updated[key] = items_out

    return updated, new_bindings, count


def migrate_diagram_file(path: Path) -> int:
    """Migrate one diagram .puml file.  Returns number of bindings added."""
    text = path.read_text(encoding="utf-8")
    fm = _parse_fm(text)
    diagram_entities = fm.get("diagram-entities")
    if not isinstance(diagram_entities, dict):
        return 0
    has_entity_ids = any(
        (isinstance(v, list) and any(isinstance(i, dict) and "entity_id" in i for i in v))
        or k == _SCOPE_KEY
        for k, v in diagram_entities.items()
    )
    if not has_entity_ids:
        return 0

    existing_bindings: list[dict[str, object]] = []
    raw_b = fm.get("bindings")
    if isinstance(raw_b, list):
        existing_bindings = [b for b in raw_b if isinstance(b, dict)]

    updated_de, new_bindings, count = _migrate_diagram_entities(diagram_entities, existing_bindings)
    if count == 0:
        return 0

    fm["diagram-entities"] = updated_de
    all_bindings = existing_bindings + new_bindings
    fm["bindings"] = all_bindings

    # Insert bindings after connections key if present, otherwise before last-updated
    reordered = _reorder_fm_with_bindings(fm)
    path.write_text(_replace_fm(text, reordered), encoding="utf-8")
    return count


def _reorder_fm_with_bindings(fm: dict[str, object]) -> dict[str, object]:
    """Produce a frontmatter dict with bindings inserted in a consistent position."""
    ordered_keys = [
        "artifact-id", "artifact-type", "name", "version", "status", "keywords",
        "diagram-type", "entity-ids-used", "connection-ids-used",
        "diagram-entities", "connections", "bindings", "last-updated",
    ]
    out: dict[str, object] = {k: fm[k] for k in ordered_keys if k in fm}
    for k, v in fm.items():
        if k not in out:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Outgoing file migration (delete c4-contains)
# ---------------------------------------------------------------------------

_C4_CONTAINS = "c4-contains"


def delete_c4_contains(path: Path) -> list[str]:
    """Remove c4-contains connections from an .outgoing.md file.

    Returns list of deleted connection ids (source---target@@c4-contains).
    """
    from src.application.modeling.artifact_write_formatting import format_outgoing_markdown
    from src.infrastructure.write.artifact_write.parse_existing import parse_outgoing_file

    parsed = parse_outgoing_file(path)
    deleted: list[str] = []
    kept: list[dict[str, object]] = []

    source = str(parsed.frontmatter.get("source-entity", ""))
    for conn in parsed.connections:
        if conn.get("connection_type") == _C4_CONTAINS:
            target = str(conn.get("target_entity", ""))
            artifact_id = f"{source}---{target}@@{_C4_CONTAINS}"
            deleted.append(artifact_id)
        else:
            kept.append(conn)

    if not deleted:
        return []

    new_text = format_outgoing_markdown(
        source_entity=source,
        version=str(parsed.frontmatter.get("version", "0.1.0")),
        status=str(parsed.frontmatter.get("status", "draft")),
        last_updated=str(parsed.frontmatter.get("last-updated", "")),
        connections=kept,
    )
    path.write_text(new_text, encoding="utf-8")
    return deleted


# ---------------------------------------------------------------------------
# Discovery and verification
# ---------------------------------------------------------------------------

_PUML_GLOB = "**/*.puml"
_OUTGOING_GLOB = "**/*.outgoing.md"
_SKIP_PREFIXES = {"_archimate-"}


def _diagram_puml_files(repo_root: Path) -> list[Path]:
    return [
        p for p in sorted(repo_root.rglob("*.puml"))
        if not any(p.name.startswith(s) for s in _SKIP_PREFIXES)
    ]


def _outgoing_md_files(repo_root: Path) -> list[Path]:
    return sorted(repo_root.rglob("*.outgoing.md"))


def _resolve_repos(extra_roots: list[Path]) -> list[Path]:
    if extra_roots:
        return [r.resolve() for r in extra_roots if r.is_dir()]

    from src.config.workspace_paths import configured_engagements, configured_repo_path, load_workspace_config

    loaded = load_workspace_config()
    if loaded is None:
        sys.exit("ERROR: No repo roots supplied and arch-workspace.yaml not found.")
    workspace_root, cfg = loaded

    roots: list[Path] = [configured_repo_path(cfg["enterprise"], workspace_root)]
    roots.append(configured_repo_path(cfg["engagement"], workspace_root))
    for _name, spec in configured_engagements(cfg).items():
        root = configured_repo_path(spec, workspace_root)
        if root not in roots and root.is_dir():
            roots.append(root)
    return [r for r in roots if r.is_dir()]


def _run_verification(repo_roots: list[Path]) -> bool:
    """Return True when all repos verify clean (no errors)."""
    from src.application.verification.artifact_verifier import ArtifactVerifier
    from src.application.verification.artifact_verifier_registry import ArtifactRegistry
    from src.application.verification.artifact_verifier_types import Severity
    from src.infrastructure.artifact_index import shared_artifact_index

    ok = True
    for root in repo_roots:
        registry = ArtifactRegistry(shared_artifact_index(root))
        results = ArtifactVerifier(registry, check_puml_syntax=False).verify_all(root)
        for r in results:
            errors = [i for i in r.issues if i.severity == Severity.ERROR]
            if errors:
                ok = False
                for e in errors:
                    print(f"  ERROR {r.path}: [{e.code}] {e.message}")
    return ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("repo_roots", nargs="*", type=Path, metavar="REPO_ROOT")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing files")
    args = parser.parse_args()

    roots = _resolve_repos(args.repo_roots)
    if not roots:
        sys.exit("ERROR: No valid repo roots found.")
    print(f"Migrating {len(roots)} repo(s): {[str(r) for r in roots]}\n")

    total_diagrams = 0
    total_bindings = 0
    total_c4_deleted: list[str] = []

    for root in roots:
        for path in _diagram_puml_files(root):
            if args.dry_run:
                text = path.read_text(encoding="utf-8")
                fm = _parse_fm(text)
                de = fm.get("diagram-entities")
                if isinstance(de, dict):
                    _, _, count = _migrate_diagram_entities(de, [])
                    if count:
                        print(f"  [dry-run] Would migrate {count} binding(s) in {path}")
                        total_diagrams += 1
                        total_bindings += count
            else:
                count = migrate_diagram_file(path)
                if count:
                    print(f"  Migrated {count} binding(s): {path}")
                    total_diagrams += 1
                    total_bindings += count

        for path in _outgoing_md_files(root):
            if args.dry_run:
                text = path.read_text(encoding="utf-8")
                if _C4_CONTAINS in text:
                    print(f"  [dry-run] Would delete c4-contains connection(s) in {path}")
            else:
                deleted = delete_c4_contains(path)
                for d in deleted:
                    print(f"  Deleted c4-contains: {d}  [{path}]")
                total_c4_deleted.extend(deleted)

    print()
    print(f"Summary: {total_diagrams} diagram(s) migrated, {total_bindings} binding(s) created, "
          f"{len(total_c4_deleted)} c4-contains connection(s) deleted.")

    if args.dry_run:
        return

    if total_diagrams or total_c4_deleted:
        print("\nRunning verifier…")
        if not _run_verification(roots):
            sys.exit("\nERROR: Migration aborted — verifier reported errors after migration.")
        print("Verifier: clean.")
    else:
        print("Nothing to migrate.")


if __name__ == "__main__":
    main()

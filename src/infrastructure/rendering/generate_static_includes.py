"""
generate_static_includes.py — Regenerate ArchiMate static include files.

Writes three files into <REPO_ROOT>/diagram-catalog/:
  _archimate-glyphs.puml      — SVG sprite definitions for all entity types
  _archimate-stereotypes.puml — skinparam blocks for all entity types
  _archimate-relations.puml   — the Rel_* macros, from each relationship's declared notation

These files are derived from the installed ontology, not from entity instance files.
Regenerate after installing a new ontology version or when first initialising a repo.

Usage:
    uv run python -m src.infrastructure.rendering.generate_static_includes [REPO_ROOT]
"""

from __future__ import annotations

import sys
from pathlib import Path

from src.config.repo_paths import DIAGRAM_CATALOG
from src.config.settings import archimate_type_markers

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sprite_key(artifact_type: str) -> str:
    return artifact_type.replace("-", "_")


def _generate_glyph_include(repo_root: Path) -> str:
    """Compose _archimate-glyphs.puml from the ontology sprite_for() methods."""
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415

    registry = get_module_registry()
    mode = archimate_type_markers()
    lines = [
        "' _archimate-glyphs.puml — generated ArchiMate glyph sprites",
        "' Auto-generated — do not edit manually.",
        "",
    ]
    if mode == "icons":
        lines.append("hide stereotype")
        lines.append("")
        for om in registry.all_ontologies().values():
            for artifact_type in sorted(om.entity_types):
                sprite_line = om.sprite_for(str(artifact_type))
                if sprite_line:
                    lines.append(sprite_line)
    return "\n".join(lines) + "\n"


_DOMAIN_COLORS: dict[str, dict[str, str]] = {
    "motivation": {
        "bg": "#EDD6F0",
        "border": "#7B3F9A",
        "grouping_bg": "#F7EEF9",
        "grouping_name": "MotivationGrouping",
    },
    "strategy": {
        "bg": "#F5DEB3",
        "border": "#8B6914",
        "grouping_bg": "#FAF0D9",
        "grouping_name": "StrategyGrouping",
    },
    "common": {
        "bg": "#E0D8CC",
        "border": "#8C7E6A",
        "grouping_bg": "#EDE8E1",
        "grouping_name": "CommonGrouping",
    },
    "business": {
        "bg": "#FFFAC8",
        "border": "#B8860B",
        "grouping_bg": "#FFFDEC",
        "grouping_name": "BusinessGrouping",
    },
    "application": {
        "bg": "#CCF2FF",
        "border": "#0078A0",
        "grouping_bg": "#E8F8FF",
        "grouping_name": "ApplicationGrouping",
    },
    "technology": {
        "bg": "#CCFFCC",
        "border": "#2E7D32",
        "grouping_bg": "#E8FFEE",
        "grouping_name": "TechnologyGrouping",
    },
    "implementation": {
        "bg": "#FFE4C4",
        "border": "#8D4E00",
        "grouping_bg": "#FFF3E8",
        "grouping_name": "ImplementationGrouping",
    },
}

_STEREOTYPE_HEADER = """\
hide stereotype

skinparam defaultFontName SansSerif
skinparam defaultFontSize 12
skinparam shadowing false
skinparam roundcorner 4
skinparam backgroundColor #FAFAFA

skinparam linetype ortho
skinparam nodesep 60
skinparam ranksep 80

skinparam rectangle<<Grouping>> {
  BackgroundColor #FFFFFF
  BorderColor #9E9E9E
  BorderStyle dashed
}
"""


def _stereotype_block(name: str, bg: str, border: str) -> str:
    return f"skinparam rectangle<<{name}>> {{\n  BackgroundColor {bg}\n  BorderColor {border}\n}}"


def _generate_stereotype_include(repo_root: Path) -> str:
    """Write _archimate-stereotypes.puml with domain colors and skinparam blocks."""
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415

    registry = get_module_registry()

    lines: list[str] = [
        "' _archimate-stereotypes.puml — ArchiMate skinparam definitions",
        "' Auto-generated — do not edit manually.",
        "",
        _STEREOTYPE_HEADER,
    ]

    # Group entity types by domain (first hierarchy element).
    domain_types: dict[str, list[str]] = {}
    for om in registry.all_ontologies().values():
        for artifact_type, info in om.entity_types.items():
            domain = info.hierarchy[0] if info.hierarchy else "common"
            domain_types.setdefault(domain, []).append(str(artifact_type))

    ordered_domains = registry.domain_order()

    for domain in ordered_domains:
        colors = _DOMAIN_COLORS.get(domain)
        if not colors:
            continue
        types_in_domain = sorted(domain_types.get(domain, []))
        if not types_in_domain:
            continue

        lines.append(f"' {'-' * 75}")
        lines.append(f"' {domain.capitalize()} layer")
        lines.append(f"' {'-' * 75}")
        lines.append(_stereotype_block(colors["grouping_name"], colors["grouping_bg"], colors["border"]))
        for artifact_type in types_in_domain:
            key = _sprite_key(artifact_type)
            lines.append(_stereotype_block(key, colors["bg"], colors["border"]))
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


#: Direction-hinted variants a body may call, and the PlantUML direction each inserts. An author
#: reaching for `Rel_Realization_Up` is stating a layout preference about one edge; without the
#: variant defined, that line draws nothing at all.
_MACRO_DIRECTIONS: tuple[tuple[str, str], ...] = (
    ("", ""), ("_Up", "up"), ("_Down", "down"), ("_Left", "left"), ("_Right", "right"),
)


def _macro_name(conn_type: str) -> str:
    """`archimate-realization` → `Rel_Realization`, the spelling the bodies already call."""
    return "Rel_" + "".join(part.capitalize() for part in conn_type.removeprefix("archimate-").split("-"))


def _generate_relations_include() -> str:
    """Compose `_archimate-relations.puml` from the ontology's declared notations.

    Generated for the reason the glyphs and stereotypes are: it is a *spelling* of what the
    ontology declares, and every hand-maintained copy of a declaration this project has had
    eventually disagreed with it. This one did twice over — it drew `archimate-influence` dotted
    where the ontology declares dashed, and it defined nine macros for a catalogue of twelve
    relationships, so a body reaching for a composition, an aggregation, an assignment, a
    specialization or a flow called a macro that does not exist and drew nothing.

    The arrow comes from `puml_arrow`, which `test_arrow_spells_the_notation` holds equal to the
    notation's own derivation, so this file and the graph canvas cannot draw the same relation two
    ways.
    """
    from src.application.puml_arrow_tokens import insert_arrow_direction  # noqa: PLC0415
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415

    lines = [
        "' _archimate-relations.puml — generated ArchiMate relationship macros (Rel_* syntax)",
        "' Auto-generated — do not edit manually.",
        "' Include after _archimate-stereotypes.puml / _archimate-glyphs.puml.",
        "",
    ]
    archimate = sorted(
        (str(name), info)
        for name, info in get_module_registry().all_connection_types().items()
        if str(name).startswith("archimate-")
    )
    for name, info in archimate:
        for suffix, direction in _MACRO_DIRECTIONS:
            spelled = (
                insert_arrow_direction(info.puml_arrow, direction) if direction else info.puml_arrow
            )
            lines.append(f"!define {_macro_name(name)}{suffix}(from, to, label) from {spelled} to")
    return "\n".join(lines) + "\n"


def static_include_contents(repo_root: Path) -> dict[str, str]:
    """What the generated include files should contain, given the ontology as loaded now.

    Composed rather than written, so the staleness check can compare against disk without
    touching it — a check that repairs what it is checking cannot fail twice, and would
    silently launder drift in CI.
    """
    return {
        "_archimate-glyphs.puml": _generate_glyph_include(repo_root),
        "_archimate-stereotypes.puml": _generate_stereotype_include(repo_root),
        "_archimate-relations.puml": _generate_relations_include(),
    }


def generate_static_includes(repo_root: Path) -> None:
    """Write the generated include files to *repo_root*. Idempotent."""
    catalog = repo_root / DIAGRAM_CATALOG
    catalog.mkdir(parents=True, exist_ok=True)
    for name, content in static_include_contents(repo_root).items():
        (catalog / name).write_text(content, encoding="utf-8")


def stale_static_includes(repo_root: Path) -> list[str]:
    """Names of generated include files that differ from what the ontology says today.

    These are committed generated artifacts, and `arch-init` is the only thing that
    rewrites them — so an ontology sprite or stereotype change leaves every repository
    that merely upgraded carrying the previous glyphs, with nothing failing. Same class of
    drift `types.generated.ts` is gated against, and gated the same way.
    """
    catalog = repo_root / DIAGRAM_CATALOG
    stale: list[str] = []
    for name, expected in static_include_contents(repo_root).items():
        path = catalog / name
        on_disk = path.read_text(encoding="utf-8") if path.exists() else None
        if on_disk != expected:
            stale.append(name)
    return sorted(stale)


def main() -> None:
    check_only = "--check" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--check"]
    if args:
        repo_root = Path(args[0]).resolve()
    else:
        from src.config.workspace_paths import resolve_workspace_repo_roots  # noqa: PLC0415

        roots = resolve_workspace_repo_roots(Path.cwd())
        if roots is None:
            print(
                "ERROR: no repo_root argument provided and no workspace configuration found. "
                "Run arch-init or provide arch-workspace.yaml.",
                file=sys.stderr,
            )
            sys.exit(1)
        repo_root = roots[0]

    if not repo_root.is_dir():
        print(f"ERROR: repo_root does not exist: {repo_root}", file=sys.stderr)
        sys.exit(1)

    if check_only:
        stale = stale_static_includes(repo_root)
        if stale:
            print(
                "ERROR: generated include files are stale against the current ontology: "
                + ", ".join(stale)
                + "\nRegenerate with: uv run python -m "
                + f"src.infrastructure.rendering.generate_static_includes {repo_root}",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"static includes up to date → {repo_root / DIAGRAM_CATALOG}")
        return

    generate_static_includes(repo_root)
    written = ", ".join(sorted(static_include_contents(repo_root)))
    print(f"Written {written} → {repo_root / DIAGRAM_CATALOG}")


if __name__ == "__main__":
    main()

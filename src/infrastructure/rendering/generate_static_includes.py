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
from typing import Any

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


_STEREOTYPE_HEADER = """\
hide stereotype

skinparam defaultFontName SansSerif
skinparam defaultFontSize 12
skinparam shadowing false
skinparam roundcorner 4
skinparam backgroundColor #FAFAFA
skinparam defaultTextAlignment center

skinparam linetype ortho
skinparam nodesep 60
skinparam ranksep 80

skinparam rectangle<<Grouping>> {
  BackgroundColor #FFFFFF
  BorderColor #9E9E9E
  BorderStyle dashed
}
"""


#: How far a corner is cut or rounded, in points. One number per style, because the *style* is the
#: declaration and this is the renderer's rendition of it — the ontology says `diagonal`, not `12`.
_CORNER_SIZE: dict[str, int] = {"rounded": 14, "diagonal": 10}


#: What an open container is filled with and drawn in. White rather than `transparent`, which
#: PlantUML honours inconsistently across output formats, and near-black rather than the domain's
#: derived border: the line is the whole of the box, so it has to read as one.
_OPEN_CONTAINER_FILL = "#FFFFFF"
_OPEN_CONTAINER_BORDER = "#1F1F1F"


def _stereotype_block(
    name: str, bg: str, border: str, corner: str = "square", outline: str = "solid",
) -> str:
    """One skinparam block: fill, line, the corners this element's category is drawn with, and
    whether it is an open container.

    `square` adds nothing — PlantUML's default rectangle is already square, and stating a
    `RoundCorner 0` would be a declaration where the absence is the answer.

    A `dashed` outline replaces the fill and the border rather than adding to them. An open container
    holds other elements, so keeping the domain colour would put a coloured plane behind them, and
    keeping the derived border would draw a line the same weight as theirs — the two properties the
    ontology declares separately are one rendition here.
    """
    if outline == "dashed":
        bg, border = _OPEN_CONTAINER_FILL, _OPEN_CONTAINER_BORDER
    lines = [f"skinparam rectangle<<{name}>> {{", f"  BackgroundColor {bg}", f"  BorderColor {border}"]
    if outline == "dashed":
        lines.append("  BorderStyle dashed")
    if corner == "rounded":
        lines.append(f"  RoundCorner {_CORNER_SIZE['rounded']}")
    elif corner == "diagonal":
        lines.append(f"  DiagonalCorner {_CORNER_SIZE['diagonal']}")
    lines.append("}")
    return "\n".join(lines)


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

    # Group entity types by domain (first hierarchy element), keeping the ontology that declared
    # each one: colour and corners are that ontology's statement, not a global table.
    domain_types: dict[str, list[tuple[str, Any]]] = {}
    appearance_by_domain: dict[str, Any] = {}
    for om in registry.all_ontologies().values():
        for artifact_type, info in om.entity_types.items():
            domain = info.hierarchy[0] if info.hierarchy else "common"
            domain_types.setdefault(domain, []).append((str(artifact_type), info))
            appearance_by_domain.setdefault(domain, om.element_appearance)

    for domain in registry.domain_order():
        appearance = appearance_by_domain.get(domain)
        fill = appearance.color_for(domain) if appearance is not None else None
        if not fill or appearance is None:
            continue
        types_in_domain = sorted(domain_types.get(domain, []), key=lambda pair: pair[0])
        if not types_in_domain:
            continue

        border = appearance.border_for(fill)
        lines.append(f"' {'-' * 75}")
        lines.append(f"' {domain.capitalize()} layer")
        lines.append(f"' {'-' * 75}")
        # A container is the domain's colour, receding — the same rule a de-emphasized element
        # uses, rather than a second tint declared beside the first.
        lines.append(_stereotype_block(
            f"{domain.capitalize()}Grouping", appearance.de_emphasized(fill), border,
        ))
        for artifact_type, info in types_in_domain:
            lines.append(_stereotype_block(
                _sprite_key(artifact_type), fill, border,
                appearance.corner_for(info.classes),
                appearance.outline_for(info.classes),
            ))
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


def stale_generated_headers(repo_root: Path) -> list[str]:
    """Diagram bodies whose generated header disagrees with what the renderer states today.

    A stored body carries a header the author did not write: the ArchiMate declarations, which it
    may hold as an `!include` marker or as the expansion itself, and the label width bound. Both
    forms of the first are permitted and the expansion is a copy. `stale_static_includes` above
    gates the include files against the ontology — this gates every body against the same answer,
    because the copy was only ever refreshed as a side effect of regenerating the body. Nine
    diagrams here were drawing the palette and the access line style they were authored with, and
    the same nine had never received the label bound: their content simply had not changed since.

    Asked of the renderer, which reads the include files from disk — so `stale_static_includes`
    has to have passed first, or two copies of the same drift could agree. `main` runs them in that
    order and stops on the first.

    Asked of the renderer, so a notation that states nothing generated is silent rather than
    exempted. Reported rather than repaired: a diagram body is an artifact, so bringing one level
    again is a write, and writes go through the write path — which refreshes the header on every
    edit, so the repair is an edit of the named diagram and nothing else.
    """
    from src.application.repo_path_helpers import diagram_source_root  # noqa: PLC0415
    from src.domain.ontology_representation.ontology_protocol import (  # noqa: PLC0415
        GeneratedHeaderRefreshingRenderer,
    )
    from src.domain.repository.frontmatter import body_after_frontmatter, parse_frontmatter  # noqa: PLC0415
    from src.infrastructure.diagram_type_registry import get_diagram_type  # noqa: PLC0415
    from src.infrastructure.rendering.puml_runtime import is_render_scratch  # noqa: PLC0415

    root = diagram_source_root(repo_root)
    stale: list[str] = []
    for path in sorted(root.rglob("*.puml")):
        if is_render_scratch(path):
            continue
        text = path.read_text(encoding="utf-8")
        diagram_type = str(parse_frontmatter(text).get("diagram-type", ""))
        if not diagram_type:
            continue
        try:
            renderer = get_diagram_type(diagram_type).renderer
        except Exception:  # noqa: BLE001 - a type this build does not carry is not this gate's business
            continue
        if not isinstance(renderer, GeneratedHeaderRefreshingRenderer):
            continue
        body = body_after_frontmatter(text)
        if renderer.refresh_generated_header(body, repo_root) != body:
            stale.append(str(path.relative_to(root)))
    return stale


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
        stale_bodies = stale_generated_headers(repo_root)
        if stale_bodies:
            print(
                "ERROR: these diagram bodies carry a generated header that disagrees with what "
                "the renderer states today:\n  " + "\n  ".join(stale_bodies)
                + "\nEach is a write: edit the diagram (artifact_edit_diagram) and the write path "
                "restates them.",
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

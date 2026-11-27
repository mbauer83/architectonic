"""Diagram PlantUML rendering helpers (PNG, SVG, and entity-body rendering)."""

from pathlib import Path

from src.application.plantuml_drawing import Drawing, Drawn, NotDrawn, PictureFormat, WhyNotDrawn
from src.application.plantuml_pictures import DRAWN
from src.application.puml_directive_policy import find_unsafe_puml_directives
from src.application.repo_path_helpers import rendered_dir_for_diagram, repo_root_for_diagram_path
from src.domain.diagrams.diagram_type_field import diagram_type_of
from src.domain.diagrams.layout.laid_out_diagram import LaidOutDiagram
from src.domain.icons.resolved_icon import IconSource
from src.domain.ontology_representation.ontology_protocol import IconPresentingRenderer
from src.infrastructure.rendering import plantuml_runner
from src.infrastructure.rendering.laid_out_rendering import (
    NoCanvasSizeError,
    drawn_from_layout,
    png_like_plantuml,
    stored_layout,
)
from src.infrastructure.rendering.native_svg import render_native_svg
from src.infrastructure.rendering.puml_runtime import plantuml_picture_key
from src.infrastructure.rendering.puml_safety import strip_leading_puml_frontmatter, strip_startuml_name
from src.infrastructure.rendering.svg_to_png import RasteriseFailedError

from .diagram_body_preparation import _prepare_diagram_puml_body
from .diagram_confidentiality import is_confidential_diagram_source
from .parse_existing import parse_diagram_file


def _confidential_render_skip(puml_path: Path) -> str | None:
    """G-f gate: return a skip-warning if this diagram is confidential, else None.

    Confidentiality is classification-driven: a *publishable* assurance diagram
    (TLP:WHITE/GREEN) renders to disk like any diagram; only confidential ones
    (above the publishability ceiling, or unclassified) are withheld.
    """
    fm = parse_diagram_file(puml_path).frontmatter
    diagram_type = diagram_type_of(fm)
    tlp = fm.get("tlp")
    if is_confidential_diagram_source(diagram_type, tlp if isinstance(tlp, str) else None):
        return (
            f"Render skipped: '{diagram_type}' is a confidential assurance diagram "
            "(G-f: confidential assurance diagrams must not write plaintext to diagram-catalog/rendered/)"
        )
    return None


def render_diagram_outputs(path: Path, warnings: list[str]) -> list[str]:
    """Render a written diagram's SVG and PNG, and report any layout failure as a failure.

    SVG first, and the PNG only if it succeeded. Both are drawn from the same body, so one verdict
    covers both — and only the SVG can *state* one: PlantUML draws a layout crash into the picture,
    and SVG is the format whose picture is readable text. Rendering the PNG first meant a crashed
    body reached disk as a stack trace under the diagram's own filename, replacing the last good
    render, before anything had established that it was a crash.

    One owner, because there were two. The create path turned a crash into an `E350` issue and the
    shared commit tail every *edit* goes through reported the same crash as a warning with
    `valid: true` — so `auto-sync` on a diagram that could no longer be drawn answered as a success.
    A caller cannot tell a rendered diagram from one whose picture is a stack trace, which is the
    whole reason the failure channel exists.
    """
    failures: list[str] = []
    try:
        offenders = find_unsafe_puml_directives(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        offenders = []
    if offenders:
        return [f"Render refused: the body references a file, URL or environment value ({offenders[0]})"]
    svg_path = _render_diagram_svg(path, warnings, failures)
    if svg_path is not None or not failures:
        png_path = _render_diagram_png(path, warnings, failures)
        if png_path:
            warnings.append(f"Rendered PNG: {png_path}")
    return failures


def _renderer_supports_edge_labels(renderer: object) -> bool:
    from src.diagram_types.c4.renderer import C4PumlRenderer  # noqa: PLC0415
    from src.infrastructure.rendering.generic_puml_renderer import GenericPumlRenderer  # noqa: PLC0415

    return isinstance(renderer, (C4PumlRenderer, GenericPumlRenderer))


def _render_diagram_entities_puml(
    diagram_type: str,
    name: str,
    diagram_entities: dict[str, object],
    diagram_connections: list[dict[str, object]] | None,
    repo_root: Path,
    *,
    edge_labels: dict[str, str] | None = None,
    candidate: object = None,
    icon_source: IconSource | None = None,
) -> str:
    from src.infrastructure.diagram_type_registry import get_diagram_type  # noqa: PLC0415

    diagram_type_mod = get_diagram_type(diagram_type)
    prepared_entities = diagram_type_mod.prepare_render_model(dict(diagram_entities), candidate)
    extra: dict[str, object] = {}
    if edge_labels and _renderer_supports_edge_labels(diagram_type_mod.renderer):
        extra["edge_labels"] = edge_labels
    if icon_source is not None and isinstance(diagram_type_mod.renderer, IconPresentingRenderer):
        extra["icon_source"] = icon_source
    return diagram_type_mod.renderer.render_body(
        name,
        [],
        [],
        diagram_type,
        repo_root,
        diagram_entities=prepared_entities,
        diagram_connections=diagram_connections,
        **extra,
    )


#: A render that failed hard, as distinct from one that was skipped or never attempted. Callers that
#: assemble a write result turn these into `E350` issues, because a caller cannot otherwise tell
#: "rendered" from "wrote a stack trace to disk" — the whole failure was reported as a warning while
#: `verification.valid` stayed `true`.
RENDER_FAILURES: str = "render_failures"


def _fail(warnings: list[str], failures: list[str] | None, message: str) -> None:
    """Record a hard render failure in both channels: prose for a person, a fact for a caller."""
    warnings.append(message)
    if failures is not None:
        failures.append(message)


#: Text PlantUML draws *into* the picture when it cannot lay a diagram out. Matched against the
#: rendered SVG, which is the only place some crashes appear at all.
_ERROR_IMAGE_MARKERS: tuple[str, ...] = ("An error has occurred", "has crashed")


def _is_error_render(stderr: str) -> bool:
    """True when PlantUML produced an error image instead of a diagram.

    PlantUML exits 0 even when graphviz layout crashes, so the return code says nothing. A stack
    trace on stderr is one signal — not, as this said, the only reliable one, and the difference
    was a repository's own diagram written and reported valid with a Java stack trace where the
    picture should be. An `EmptySvgException` out of dot's orthogonal router exits 0, prints
    *nothing* to stderr, and draws the trace into the image; `-failfast2` does not change that.
    See `_is_error_picture` for the reading that catches it.
    """
    return "Exception" in stderr


def _is_error_picture(svg: str) -> bool:
    """True when a rendered SVG is PlantUML's error picture rather than the diagram.

    The picture is the only place the failure is stated, so the picture is what is read. SVG is
    text and carries the message verbatim, which is why the check lives on this format — a PNG of
    the same body would need pixels read back to say the same thing.
    """
    return any(marker in svg for marker in _ERROR_IMAGE_MARKERS)


def _render_diagram_png(
    puml_path: Path, warnings: list[str], failures: list[str] | None = None
) -> Path | None:
    """Render a PUML file to PNG using PlantUML. Returns the PNG path or None."""
    repo_root = repo_root_for_diagram_path(puml_path) or puml_path.parent.parent.parent
    rendered_dir = rendered_dir_for_diagram(puml_path, repo_root)
    rendered_dir.mkdir(parents=True, exist_ok=True)

    # The @startuml..@enduml block, without the frontmatter above it.
    content = strip_leading_puml_frontmatter(puml_path.read_text(encoding="utf-8"))
    start = content.find("@startuml")
    end = content.find("@enduml")
    if start == -1 or end == -1:
        warnings.append("Cannot render: @startuml/@enduml markers not found")
        return None

    puml_body = content[start : end + len("@enduml")]
    diagram_type = diagram_type_of(parse_diagram_file(puml_path).frontmatter)

    if (skip := _confidential_render_skip(puml_path)) is not None:
        warnings.append(skip)
        return None

    puml_body = _prepare_diagram_puml_body(puml_body, repo_root, diagram_type)

    # Without the diagram's name, as every render prepares a body: the picture is then the preview's,
    # and so is the key it is kept by.
    puml_body_for_render = strip_startuml_name(puml_body)
    if (native_svg := render_native_svg(puml_body_for_render, diagram_type)) is not None:
        return _rasterise_svg(native_svg, rendered_dir / f"{puml_path.stem}.png", warnings, failures)
    if _laid_out(puml_path) is not None:
        # Drawn from the SVG just composed, which is the picture: PlantUML never draws a laid-out one.
        composed = rendered_dir / f"{puml_path.stem}.svg"
        if not composed.exists():
            return None
        return _rasterise_svg(composed.read_text(encoding="utf-8"), composed.with_suffix(".png"), warnings, failures)

    final = rendered_dir / f"{puml_path.stem}.png"
    match _drawn(puml_body_for_render, "png"):
        case NotDrawn(why=WhyNotDrawn.NO_PLANTUML):
            warnings.append("plantuml.jar not found; render skipped")
            return None
        case NotDrawn() as failed:
            warnings.append(f"PlantUML render error: {failed.reason}")
            return None
        case Drawn(refusals=(first, *_)) as drawn:
            _fail(warnings, failures, f"PlantUML render failed: {first.message} {drawn.diagnostics[:200]}".rstrip())
            return None
        case Drawn(diagnostics=said) if _is_error_render(said):
            _fail(
                warnings,
                failures,
                f"PlantUML produced an error image (layout failure), previous render kept: {said[:200]}",
            )
            return None
        case Drawn(picture=bytes() as picture):
            final.write_bytes(picture)
            return final
        case Drawn():
            return None


def _drawn(source: str, fmt: PictureFormat) -> Drawing:
    """What PlantUML draws of a prepared body: the picture is handed back, not left in a directory."""
    return plantuml_runner.PLANTUML.draw(source, fmt)


def _rasterise_svg(svg: str, final: Path, warnings: list[str], failures: list[str] | None) -> Path | None:
    """The PNG of a picture PlantUML did not draw as it stands — a diagram type's own SVG, or a laid-out one.

    The menu and the download route offer PNG for every diagram, and a type that owns its SVG notation
    used to answer that with nothing but advice to save first — which could never produce one (B88).
    """
    try:
        final.write_bytes(png_like_plantuml(svg))
    except (RasteriseFailedError, NoCanvasSizeError) as exc:
        _fail(warnings, failures, f"PNG render failed: {exc}")
        return None
    return final


def _laid_out(puml_path: Path) -> LaidOutDiagram | None:
    """The layout the stored diagram is drawn from, joined to its picture; None for PlantUML's own arrangement."""
    from src.infrastructure.app_bootstrap import process_runtime_catalogs  # noqa: PLC0415

    return stored_layout(puml_path, process_runtime_catalogs().ontology)


def _render_diagram_svg(
    puml_path: Path, warnings: list[str], failures: list[str] | None = None
) -> Path | None:
    """Render a PUML file to SVG using PlantUML. Returns the SVG path or None."""
    repo_root = repo_root_for_diagram_path(puml_path) or puml_path.parent.parent.parent
    rendered_dir = rendered_dir_for_diagram(puml_path, repo_root)
    rendered_dir.mkdir(parents=True, exist_ok=True)

    content = strip_leading_puml_frontmatter(puml_path.read_text(encoding="utf-8"))
    start = content.find("@startuml")
    end = content.find("@enduml")
    if start == -1 or end == -1:
        return None

    puml_body = content[start : end + len("@enduml")]
    diagram_type = diagram_type_of(parse_diagram_file(puml_path).frontmatter)

    if (skip := _confidential_render_skip(puml_path)) is not None:
        warnings.append(skip)
        return None

    puml_body = _prepare_diagram_puml_body(puml_body, repo_root, diagram_type)
    puml_body_for_render = strip_startuml_name(puml_body)
    if (native_svg := render_native_svg(puml_body_for_render, diagram_type)) is not None:
        final = rendered_dir / f"{puml_path.stem}.svg"
        final.write_text(native_svg, encoding="utf-8")
        return final

    # The picture of this very body drawn before — when the editor read it, or by the render before this
    # one — is the picture PlantUML would draw now (`plantuml_pictures`).
    key = plantuml_picture_key(puml_body_for_render, "svg")
    if (kept := DRAWN.recall(key)) is not None and not _is_error_picture(kept.decode("utf-8")):
        return _write_composed(kept, puml_path, rendered_dir, warnings)

    match _drawn(puml_body_for_render, "svg"):
        case NotDrawn(why=WhyNotDrawn.NO_PLANTUML):
            warnings.append("plantuml.jar not found; SVG render skipped")
            return None
        case NotDrawn() as failed:
            warnings.append(f"SVG render error: {failed.reason}")
            return None
        case Drawn(refusals=(first, *_)) as drawn:
            _fail(warnings, failures, f"SVG render failed: {first.message} {drawn.diagnostics[:200]}".rstrip())
            return None
        case Drawn(picture=bytes() as picture, diagnostics=said) if _is_error_render(said) or _is_error_picture(
            picture.decode("utf-8", errors="replace")
        ):
            _fail(
                warnings,
                failures,
                "PlantUML produced an error image (layout failure), previous render kept: "
                f"{said[:200] or 'no stderr; the failure is drawn into the picture'}",
            )
            return None
        case Drawn(picture=bytes() as picture):
            DRAWN.keep(key, picture)
            return _write_composed(picture, puml_path, rendered_dir, warnings)
        case Drawn():
            warnings.append("SVG render produced no output")
            return None


def _write_composed(picture: bytes, puml_path: Path, rendered_dir: Path, warnings: list[str]) -> Path:
    """Write PlantUML's SVG of *puml_path*, composed from the layout the diagram states, as its rendering."""
    final = rendered_dir / f"{puml_path.stem}.svg"
    svg, composing = drawn_from_layout(picture.decode("utf-8"), _laid_out(puml_path))
    warnings.extend(composing)
    final.write_text(svg, encoding="utf-8")
    return final

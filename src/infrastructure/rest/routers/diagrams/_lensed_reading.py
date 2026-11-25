"""The body a reader's lens asks PlantUML to draw: the diagram restyled, explained, and held to its layout.

Both image routes (`_serving`) render through `reading_body`, so "show me this" and "export what I
am looking at" are one body. On a laid-out diagram whose reader prints attributes the body is drawn
once more to measure it: a printed line that would draw its element wider than the stored picture is
broken (`printed_lines_held`), so the element grows downward in its column rather than over its
neighbour. Nothing here moves a neighbour.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.viewpoints.diagram_reading_lens import ReadingLens
from src.domain.diagrams.layout.laid_out_diagram import LaidOutDiagram
from src.infrastructure.rest.routers import state as s


def declared_type_labels(catalogs: RuntimeCatalogs) -> dict[str, str]:
    """What each element type is called, where its own name is not it — keyed as a legend spells it.

    The ontology states this (`EntityTypeInfo.label`) so that every surface naming a type for a reader
    says the same thing; the legend takes it rather than deriving a second answer. Keyed on the spaced
    lower-case form because that is what `readable_label` has in hand at the point it decides.
    """
    return {
        info.artifact_type.replace("-", " "): info.label
        for info in catalogs.ontology.all_entity_types().values()
        if info.label
    }


def kind_muting(lens: ReadingLens, repo_root: Path) -> Callable[[str], str] | None:
    """How a reading turns the element-kind colouring down, applied to the *prepared* body.

    Not to the lensed body, and that is measured rather than chosen: preparation restates every
    stereotype declaration from the ontology — one owner for what a kind looks like — so a muted
    declaration written earlier survives as a block and comes back in the authored colour. After
    preparation is the one point at which a body is final.

    `None` when nothing is to be muted, so the render path takes its ordinary route.
    """
    from src.application.viewpoints.diagram_reading_lens import ElementKindColouring  # noqa: PLC0415
    from src.infrastructure.rendering._archimate_includes import ArchimateDeclarations  # noqa: PLC0415
    from src.infrastructure.rendering.diagram_kind_muting import (  # noqa: PLC0415
        body_with_muted_element_kinds,
    )

    if lens.element_kind_colouring is not ElementKindColouring.MUTED or not lens.colour_by:
        return None
    declarations = ArchimateDeclarations.from_repo(repo_root)
    return lambda prepared: body_with_muted_element_kinds(
        prepared, lens=lens, declarations=declarations
    )


def lensed_body(
    artifact_id: str,
    diagram_path: Path,
    lens: ReadingLens,
    catalogs: RuntimeCatalogs,
    repo_root: Path,
    wrapped: Callable[[str, tuple[str, ...]], tuple[str, ...]] | None = None,
) -> str:
    """The diagram's body with the lens applied, or its authored body when the lens is empty.

    The entities are resolved by `resolve_placed_entities` — the same function the attribute panel
    asks — so a reader cannot be offered an attribute here that the panel would not have listed, nor
    the other way round. The snapshot comes from `configured_registry_snapshot`, so the lens reads
    attributes under exactly the reach the rest of the surface uses.

    The catalogues are *given*, not read from process state: they arrive through the same freshness
    dependency the attribute panel takes, which is what lets a test override them and what
    `test_runtime_catalogs_have_one_accessor` requires of a router. It caught this module reading them
    directly.
    """
    from src.application.viewpoints.diagram_attribute_panel import (  # noqa: PLC0415
        offers_for_diagram,
        palette_members,
        palette_unset,
    )
    from src.application.viewpoints.diagram_reading_lens import apply_reading_lens  # noqa: PLC0415
    from src.application.viewpoints.placed_occurrences import (  # noqa: PLC0415
        placed_connection_triples,
        resolve_placed_entities,
    )
    from src.infrastructure.rendering.diagram_legend_for_reading import (  # noqa: PLC0415
        body_with_reading_legend,
    )
    from src.infrastructure.rendering.diagram_notation_in_use import notation_in_use  # noqa: PLC0415
    from src.infrastructure.viewpoints_snapshot import configured_registry_snapshot  # noqa: PLC0415
    from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file  # noqa: PLC0415

    body = parse_diagram_file(diagram_path).puml_body
    if lens.is_empty:
        return body
    repo = s.get_repo()
    diag_rec = repo.get_diagram(artifact_id)
    if diag_rec is None:
        return body
    _, registry, _ = s.get_write_deps(catalogs)
    registries = configured_registry_snapshot(catalogs, repo.repo_roots)
    entities = resolve_placed_entities(dict(diag_rec.extra), registry)
    # The same offers the panel showed the reader, so "palette or ramp" is decided once and the
    # picture, its legend and the controls cannot disagree about an attribute. Resolved here rather
    # than inside either consumer because both need the answer and it is one lookup.
    offers = offers_for_diagram(
        entities,
        repo_root,
        specialization_catalog=catalogs.specializations,
        profile_registry=catalogs.profiles,
    ) if lens.colour_by else None
    palette = palette_members(offers, lens.colour_by) if offers is not None else ()
    # The member a schema declares as its default: what a reader sees on an entity nobody has
    # assessed, so it is drawn as unset rather than given a place on the scale.
    unset = palette_unset(offers, lens.colour_by) if offers is not None else None
    lensed = apply_reading_lens(
        body, entities, lens=lens, read_access=repo, registries=registries, palette=palette,
        unset=unset, wrapped=wrapped,
    )
    if not lens.legend:
        return lensed
    # The legend composes over the lensed body rather than being woven into it: it is appended, and
    # keeping it a second step is what lets a reader ask for one on an otherwise untouched diagram.
    notation = notation_in_use(
        body,
        placed_connection_triples(dict(diag_rec.extra), registry),
        repo_root=repo_root,
        relation_notations=catalogs.connections.all_relation_notations(),
    )
    return body_with_reading_legend(
        lensed,
        lens=lens,
        declarations=notation.declarations,
        members=palette,
        unset=unset,
        declared_labels=declared_type_labels(catalogs),
        connection_notations=notation.connection_notations,
        nested_types=notation.nested_types,
    )


def reading_body(
    artifact_id: str,
    diagram_path: Path,
    lens: ReadingLens,
    catalogs: RuntimeCatalogs,
    repo_root: Path,
    *,
    diagram_type: str | None,
    laid_out: LaidOutDiagram | None,
    stored_svg: Path | None,
) -> str:
    """The body to draw for *lens*: `lensed_body`, its printed lines held to *stored_svg*'s widths.

    Held only where it can matter: the diagram states a layout (without one PlantUML arranges around
    whatever the lens adds), the reader prints something, and the stored picture is there to say how
    wide each element is meant to be.
    """
    from src.infrastructure.rendering.diagram_builder import render_puml_svg  # noqa: PLC0415
    from src.infrastructure.rendering.printed_lines_held import printed_lines_held  # noqa: PLC0415

    body = lensed_body(artifact_id, diagram_path, lens, catalogs, repo_root)
    if laid_out is None or not lens.printed or stored_svg is None:
        return body
    measured, _warnings = render_puml_svg(
        body, repo_root, diagram_type, restyle_prepared=kind_muting(lens, repo_root)
    )
    wrapped = printed_lines_held(measured, stored_svg.read_text(encoding="utf-8")) if measured else None
    return body if wrapped is None else lensed_body(artifact_id, diagram_path, lens, catalogs, repo_root, wrapped)

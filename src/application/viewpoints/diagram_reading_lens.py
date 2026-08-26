"""An ad-hoc reading of one diagram: colour by an attribute, print attributes with the elements.

**A reading, not an edit.** What a reader chooses here lives as long as their visit to the page and is
never written back — no frontmatter changes, no saved viewpoint, no persisted display option. The
diagram's own body is read, restyled in memory, and rendered; the next request without a lens renders
the diagram as it is authored. That decides the whole shape of this module: it takes a body and gives
back a body, and it has nowhere to put state even if it wanted one.

**Expressed as a viewpoint presentation, because that is what it is.** "Colour these elements by this
attribute, interpolating between two endpoints" is a `mode="scale"` style rule, and this repository
already has the machinery that reads one: `calculate_scale_bounds` computes deterministic bounds over
the complete drawn set, `evaluate_item_style` resolves a per-item position, and the outcome
classification says whether a rule engaged. A lens that computed its own bounds would be a second
answer to "what are this attribute's extremes on this diagram" — and it would get the ordinal case
wrong the way the first version of the pinned-scale path did, by taking the drawn extremes for a
declared range and calling the mildest value on the diagram "worst".

So the lens *synthesises a rule* and asks the existing evaluator. The reader's choice becomes a
`StyleRule`; everything after that is the code the viewpoint surfaces already use.

**The reader chooses the colours, not only the attribute.** A gradient's two ends and any member's
colour can be overridden, and neither requires authoring anything: two readers colouring by two
different attributes are not obliged to want the same two colours. An override is *partial* — a member
with no colour of its own keeps the one its declared position gives it — so changing one does not mean
restating the rest. What an override cannot be is anything other than `#rrggbb`: these colours are
written into a PUML declaration whose compound colour form is `;`-separated, so the route that accepts
them refuses everything else rather than trusting a caller.

**Nothing here names an attribute, a type, or a diagram family.** Which attributes exist is a profile
question (`diagram_attribute_panel` asks it), whether one has an order is a declared level of
measurement (`attribute_scales` answers it), and what a token paints as is the style-value table's
answer. This module knows only that a reader named something and that the machinery either read it or
did not.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from src.application.puml_alias_declarations import alias_declared_on, restyled_declaration
from src.domain.hex_colors import readable_ink
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.viewpoints.viewpoint_condition_evaluation import read_attribute_value
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_criteria import AttributeCondition, EntityCriteriaGroup, ValueRef
from src.domain.viewpoints.viewpoint_evaluation_context import CriteriaReadAccess, EvaluationEnvironment
from src.domain.viewpoints.viewpoint_scale_styling import (
    ScaleStyleValue,
    calculate_scale_bounds,
)
from src.domain.viewpoints.viewpoint_style_evaluation import evaluate_item_style
from src.domain.viewpoints.viewpoint_style_values import (
    AD_HOC_RAMP_TOKENS,
    categorical_colors,
    interpolate_style_colors,
    token_color,
)
from src.domain.viewpoints.viewpoints import PresentationSpec, StyleRule

#: The border every restyled element takes. One colour rather than a computed one: the fill carries the
#: reading and a border that also varied would compete with it.
_BORDER = "48391c"


@dataclass(frozen=True)
class ReadingLens:
    """What a reader asked to see, for this request only.

    Empty is the authored diagram. Both fields are attribute *names*, not per-type choices: an
    attribute is one thing wherever it occurs, so colouring by `risk_score` colours every drawn entity
    that has one, on one scale. The panel groups its offer by type because *availability* is per type —
    which attributes a type declares — and that grouping is a fact about the menu, not about the dish.
    """

    colour_by: str = ""
    printed: tuple[str, ...] = ()
    #: The reader's own gradient for a continuous attribute, as two `#rrggbb` colours, or None for the
    #: declared endpoints. A reader colouring by cost and a reader colouring by risk are not obliged to
    #: want the same two colours, and neither is obliged to author a rule to say so.
    ramp: tuple[str, str] | None = None
    #: The reader's own colour for individual members of a value set. Partial: a member absent here
    #: keeps the colour its declared position gives it, so changing one member's colour does not mean
    #: restating the rest.
    key: Mapping[str, str] = field(default_factory=dict)
    #: Whether the diagram should explain its own notation. One flag rather than one per mark: a
    #: reader wants the legend or does not, and which marks it can show is the diagram's answer, not
    #: theirs — four controls, three of which a given diagram cannot act on, is three dead controls.
    #: A legend goes *into* the image, so asking for one is asking for a different picture, which is
    #: why it counts as a request below even though the elements are untouched by it.
    legend: bool = False

    @property
    def is_empty(self) -> bool:
        """Whether this asks for anything.

        A mapping alone asks for nothing: it says how to colour, and without `colour_by` there is
        nothing to colour. So a stale `ramp` left in a URL cannot force a re-render of a diagram
        nobody asked to have coloured. A legend is different — nothing else can add one — so it makes
        the request non-empty on its own.
        """
        return not self.colour_by and not self.printed and not self.legend


def _ramp_rule(attribute: str, ramp: tuple[str, str] | None) -> StyleRule:
    """The reader's colour choice over an ordered attribute, as the style rule it is.

    An overridden gradient goes in as two `#rrggbb` literals where the default goes in as two tokens,
    and `token_color` passes a literal through — so the endpoints are interchangeable and the
    interpolation is the same code either way.
    """
    return StyleRule(
        capability="node_color",
        mode="scale",
        scale_attribute=attribute,
        scale_tokens=ramp if ramp is not None else AD_HOC_RAMP_TOKENS,
    )


def _member_rules(attribute: str, members: Sequence[str], key: Mapping[str, str]) -> tuple[StyleRule, ...]:
    """The reader's colour choice over an *unordered* set: one match rule per declared member.

    A ramp needs an order and these values have none — an enum's members are a set, and interpolating
    across them would put `retired` between `planned` and `active` because of where the enum happens to
    be written. So each member gets its own colour and its own rule, which is exactly what an author
    writing this by hand would produce.

    The colour goes in as a `#rrggbb` literal rather than a token, because a token names a *meaning*
    (`caution`, `critical`) and a member of an arbitrary value set has none. `is_valid_style_value`
    admits a literal for every colour capability, which is what makes this expressible at all.
    """
    return tuple(
        StyleRule(
            capability="node_color",
            mode="match",
            match_criteria=EntityCriteriaGroup(
                children=(
                    AttributeCondition(
                        attribute=attribute,
                        comparator="eq",
                        value=ValueRef(kind="literal", literal=member),
                    ),
                )
            ),
            value=key.get(member, colour),
        )
        for member, colour in categorical_colors(members)
    )


def _fill_for(value: object) -> str | None:
    """The colour one evaluated style value paints as, or None where the item is unstyled."""
    if isinstance(value, ScaleStyleValue):
        return interpolate_style_colors(value.tokens[0], value.tokens[1], value.position)
    if isinstance(value, str) and value:
        return token_color(value)
    return None


def _printed_lines(
    entity: EntityRecord,
    printed: Sequence[str],
    *,
    environment: EvaluationEnvironment,
) -> tuple[str, ...]:
    """`name: value` for each asked-for attribute this entity actually carries.

    Through `read_attribute_value`, which is the one place that knows where a value lives. An attribute
    the entity does not carry contributes no line at all rather than `owner: —`: a diagram is short of
    room, and a column of dashes spends it saying nothing.
    """
    lines: list[str] = []
    for name in printed:
        value, present = read_attribute_value(entity, name, context="entity", environment=environment)
        if present and value is not None and str(value) != "":
            lines.append(f"{name}: {value}")
    return tuple(lines)


def apply_reading_lens(
    puml_body: str,
    entities: Sequence[EntityRecord],
    *,
    lens: ReadingLens,
    read_access: CriteriaReadAccess,
    registries: RegistrySnapshot,
    palette: Sequence[str] = (),
    environment: EvaluationEnvironment | None = None,
) -> str:
    """*puml_body* with the reader's colouring and printing applied to the elements it declares.

    Element lines are found through `alias_declared_on` and rewritten through
    `restyled_declaration` — the module that owns reading and writing an alias declaration. A regex
    here would be the sixth reading of that syntax, and the register row for it records what the
    previous five cost.

    An entity is matched to a line by its `display_alias`, which is the alias the renderer emitted for
    it. A line whose alias belongs to no drawn entity — a grouping, a junction, a note — is returned
    untouched, which is the honest answer: the lens colours by an attribute, and those elements have
    none.

    **A body in, a body out.** This returned a record carrying the legends, the styled and unstyled
    counts, and the attributes that said nothing — seven fields of which the route read one. Nobody
    displayed the rest: what a reader needs to know before choosing an attribute is how many drawn
    entities carry a value, and the attribute panel already answers that from the same reading. A
    legend drawn *into* the image will need the legend data, and can introduce a return type then,
    with a consumer.
    """
    if lens.is_empty:
        return puml_body

    env = environment or EvaluationEnvironment()
    by_alias: dict[str, EntityRecord] = {e.display_alias: e for e in entities if e.display_alias}

    presentation: PresentationSpec | None = None
    bounds: Mapping[int, object] = {}
    if lens.colour_by:
        # Which of the two colourings applies is the *model's* answer, not the reader's, and it is
        # answered once — by `palette_members`, off the same offers the panel showed the reader. This
        # asked the viewpoint criteria snapshot instead, whose enum map answers a different question:
        # what *string* values a condition may compare an attribute against. It withholds a boolean's
        # two members on purpose, so a boolean attribute would have been offered two swatches here and
        # drawn as a ramp. An empty palette means a ramp, which is also what an ordinal gets: its enum
        # is a rank, and the panel already says so.
        rules = (
            _member_rules(lens.colour_by, palette, lens.key) if palette
            else (_ramp_rule(lens.colour_by, lens.ramp),)
        )
        presentation = PresentationSpec(representation="diagram", styling_rules=rules)
        # The bounds are the whole reason to call this: an ordinal's ramp spans its *declared* range,
        # not the drawn extremes, and a lens computing its own would paint the mildest value on a
        # diagram as the worst. The legends and the drift set it also returns have no reader here.
        bounds, _legends, _drift = calculate_scale_bounds(
            presentation,
            tuple((entity, "entity") for entity in entities),
            registries=registries,
            environment=env,
        )

    fills: dict[str, str] = {}
    if presentation is not None:
        for entity in entities:
            evaluation = evaluate_item_style(
                entity,
                "entity",
                presentation,
                read_access=read_access,
                registries=registries,
                environment=env,
                scale_bounds=bounds,  # type: ignore[arg-type]
            )
            fill = _fill_for(evaluation.style.get("node_color"))
            if fill is not None and entity.display_alias:
                fills[entity.display_alias] = fill

    labels: dict[str, tuple[str, ...]] = {}
    if lens.printed:
        for entity in entities:
            lines = _printed_lines(entity, lens.printed, environment=env)
            if lines and entity.display_alias:
                labels[entity.display_alias] = lines

    rewritten: list[str] = []
    for line in puml_body.splitlines():
        declaration = alias_declared_on(line)
        alias = declaration.alias if declaration is not None else ""
        if alias not in by_alias:
            rewritten.append(line)
            continue
        fill = fills.get(alias)
        rewritten.append(
            restyled_declaration(
                line,
                fill=fill.lstrip("#") if fill else None,
                border=_BORDER if fill else None,
                ink=readable_ink(fill).lstrip("#") if fill else None,
                label_lines=labels.get(alias, ()),
            )
        )

    # The trailing newline is preserved rather than always added: a body that had none is not a
    # body this function should decide to change.
    return "\n".join(rewritten) + ("\n" if puml_body.endswith("\n") else "")

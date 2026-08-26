"""The styled sibling of an execution: which items a viewpoint shows, hides, and how it paints them.

Derived from :class:`~src.domain.viewpoints.viewpoint_projection.ViewpointProjection`. Two
operations serve it and they are **not** the same shape, so they get one DTO each:
``/api/viewpoints/execute-projection`` always produces a projection and stamps the model generation
it ran against, while ``/api/diagrams/{id}/viewpoint-projection`` reads a projection a diagram may
simply not have — that one answers ``{"applied": false}`` and nothing else.

The occurrence row is shared, because it is one shape in the domain and a client renders both the
same way. It carried eight fields no decoder declared, which effect schemas silently strip: a
derived connection reached the GUI with its certainty, hop count and witness ids removed, and the
overlay had no way to tell a derived edge from a modelled one.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import RootModel

from src.infrastructure.rest.contracts.wire_shape import Closed


class ScaleStyleValueResponse(Closed):
    """A continuous style: interpolate between ``tokens`` at ``position`` (0..1).

    Never a discrete token — a ``scale`` rule declares a spectrum, and collapsing it to a band
    would report a value the rule did not compute.
    """

    position: float
    tokens: tuple[str, str]


#: What one capability is worth on an occurrence: an opaque token a surface adapter resolves, or a
#: scale position to interpolate. Opaque by design — generic code never interprets a token — but not
#: arbitrary: these are the only two forms style evaluation produces.
StyleValueResponse = str | ScaleStyleValueResponse


class ProjectedOccurrenceResponse(Closed):
    """One entity or connection, and what the viewpoint does with it.

    ``style`` is empty whenever ``reasons`` is non-empty, in every enforcement mode: style tokens
    express the viewpoint's semantics, which an excluded item by definition does not satisfy.

    The connection fields (``connection_type`` through ``via_connection_ids``) are null on an
    entity, and the entity fields (``derived_match_hops``, ``column_values``) are null on a
    connection — the row describes both kinds, and ``item_kind`` says which one it is.
    """

    item_id: str
    item_kind: Literal["entity", "connection"]
    state: Literal["visible", "ghosted"]
    membership: Literal["primary", "expanded"]
    #: Empty iff the item fully matches. ``out_of_scope`` fails the effective scope,
    #: ``criteria_mismatch`` the definition's criteria, ``endpoint_excluded`` is a connection whose
    #: own source or target is excluded.
    reasons: list[Literal["out_of_scope", "criteria_mismatch", "endpoint_excluded"]]
    style: dict[str, StyleValueResponse]
    connection_type: str | None
    source_id: str | None
    target_id: str | None
    certainty: Literal["certain", "potential"] | None
    hops: int | None
    via_connection_ids: list[str]
    #: Entities only: set when the criteria match rested on REQUIRED derived evidence — the
    #: shortest witness chain it depended on. Null for a match establishable from modelled facts.
    derived_match_hops: int | None
    #: Entities only, and only where the definition authors columns: one entry per authored source,
    #: resolved at execution time, explicitly null where it does not resolve for this entity.
    column_values: dict[str, Any] | None


class StyleRuleOutcomeResponse(Closed):
    """What one authored style rule actually did — the "no silent no-op" contract.

    ``expected-empty`` is a legitimate state (a gap rule over a healthy model) and warns nowhere;
    only ``unresolvable`` and ``shadowed`` are defects. ``disabled`` is a deliberate authoring
    state, not a failure.
    """

    rule_index: int
    capability: str
    kind: Literal["applied", "expected-empty", "shadowed", "unresolvable", "disabled"]
    matched_count: int
    applied_count: int
    #: What went wrong, where anything did — typically the attribute path that cannot resolve.
    detail: str | None


class ScaleLegendResponse(Closed):
    """A scale's resolved bounds and endpoint tokens, so a legend can be drawn without re-deriving
    the data range the styling used.

    The labels are what the endpoints are *called*, and they are `null` wherever the numbers are the
    answer. An ordinal attribute is positioned by its declared rank, so a legend reading `0 → 4` for
    `negligible → catastrophic` reports how the ramp is computed rather than what it shows — the words
    are the scale the model declared, and the ranks are an implementation detail of reading it.
    """

    capability: str
    attribute: str
    minimum: float
    maximum: float
    tokens: tuple[str, str]
    minimum_label: str | None = None
    maximum_label: str | None = None


class ViewpointProjectionResponse(Closed):
    """The repository projection for an executed viewpoint.

    ``applied`` is always true here: this operation *computes* a projection, so there is no
    unprojected outcome to report. It is on the body because the diagram route's response carries
    the same key and a client reads both through one branch.

    ``index_generation`` is the same provenance contract ``/execute`` publishes, so a caller
    correlating a result with its styling can verify both came from one model snapshot.
    """

    applied: Literal[True]
    index_generation: int | None
    target: Literal["repository"]
    items: list[ProjectedOccurrenceResponse]
    #: Artifact-local only, and therefore always false here — a repository projection pins no
    #: version to be stale against.
    stale_pin: bool
    #: Schema drift, capability drift, unresolved references. Degraded loudly, never silently.
    warnings: list[str]
    scale_legends: list[ScaleLegendResponse]
    rule_outcomes: list[StyleRuleOutcomeResponse]


class NoDiagramViewpointResponse(Closed):
    """The artifact pins no viewpoint, so there is no projection and nothing else to say.

    The ordinary case rather than an error — most diagrams are hand-drawn — which is why it is a 200
    with a one-key body and not a 404.
    """

    applied: Literal[False]


class AppliedDiagramViewpointResponse(Closed):
    """The projection a diagram or matrix saved in its own frontmatter.

    ``stale_pin`` is what this route carries that the repository projection cannot: the artifact
    pinned a version, and the definition has since moved past it.
    """

    applied: Literal[True]
    target: Literal["diagram", "matrix"]
    items: list[ProjectedOccurrenceResponse]
    stale_pin: bool
    warnings: list[str]
    scale_legends: list[ScaleLegendResponse]
    rule_outcomes: list[StyleRuleOutcomeResponse]


class DiagramViewpointProjectionResponse(
    RootModel[NoDiagramViewpointResponse | AppliedDiagramViewpointResponse]
):
    """Two genuinely different answers, told apart by ``applied``.

    A flat model with every projection field optional would have been the smaller diff and the worse
    contract: it makes a client null-check ``items`` on the branch where the server guarantees them,
    and it cannot say that ``applied: false`` means *exactly* one key. Not ``NullsOmitted`` either —
    ``response_model_exclude_none`` reaches into nested models, and it would have stripped the nulls
    off every :class:`ProjectedOccurrenceResponse` here while the repository projection sends them,
    leaving one shape with two null policies.

    A ``RootModel`` so the document carries a named component: a bare ``A | B`` on the route
    publishes an inline union a generated client cannot refer to.

    No ``Field(discriminator=...)``, unlike the other unions on this surface, and for a mechanical
    reason: pydantic writes the discriminator mapping with Python's spelling of the key, so a
    *boolean* tag becomes ``"True"``/``"False"`` in the document and the TypeScript generator then
    emits ``applied: "True"`` — a string where the body carries a bool. The arms are closed and their
    tags are ``const``, so validation resolves them without the mapping, and the published ``anyOf``
    is the truthful one.
    """

    root: NoDiagramViewpointResponse | AppliedDiagramViewpointResponse


class AttributeOfferResponse(Closed):
    """One attribute, as a reading control can offer it.

    ``colour`` is what a colour control may do with it, decided by what the ontology declares rather
    than by the attribute's name: ``ramp`` where there is an order — a number, a date, or an ordinal
    whose rank `x-scale: ordinal` declares — ``palette`` where there is a bounded value set with no
    inherent order, and ``none`` for free text and lists, where a ramp would be meaningless and a
    palette one colour per entity.

    There is no ``printable`` flag: every attribute can be printed beside its entity, whatever its
    colour, so a field carrying one value for every row would say nothing.

    ``present_on`` is how many of the drawn entities of this type carry a value, and **zero is
    reported rather than hidden**. A dropped row would say "this type has no such attribute", which is
    false, and a reader who cannot see the attribute cannot learn why nothing is coloured.
    """

    name: str
    declared_type: str
    colour: Literal["ramp", "palette", "none"]
    values: list[str]
    present_on: int


class TypeOfferResponse(Closed):
    """One entity type, or one specialization of it, as it occurs on this diagram.

    A specialization is its own row because it contributes its own attributes: two entities of one
    type carrying different specializations do not offer the same set, and merging them would offer
    each the other's. ``specialization`` is empty for the bare type.
    """

    entity_type: str
    specialization: str
    drawn: int
    attributes: list[AttributeOfferResponse]


class SharedAttributeOfferResponse(Closed):
    """One attribute more than one drawn row declares identically.

    Colouring is by attribute *name* and applies to every drawn entity that has one, so an attribute
    several types share is a reading of the whole diagram. ``on_rows`` names those rows — as
    ``type`` or ``type/specialization`` — because a reader weighing a global colouring needs to know
    over what. The nested ``present_on`` counts *entities* diagram-wide, not the sum of the per-row
    counts: an entity carrying two specializations appears under each and would be counted twice.
    """

    attribute: AttributeOfferResponse
    on_rows: list[str]


class DiagramAttributePanelResponse(Closed):
    """What a reader can do with the attributes of the entities one diagram draws.

    Only the types the diagram actually draws *and* that declare something to choose from — the same
    convention every legend in the product keeps: list what is present. The declared vocabulary is much
    larger, and offering it is the difference between a menu and a catalogue; a type with no attributes
    is a fold that opens on nothing, and which types are drawn is what the entity list beside this
    answers.

    ``shared`` comes first because it is what reads across the picture. Its members are still listed
    inside their own ``types`` entries, where the per-type presence count lives — the shared row is a
    shortcut to the same choice, not a move.

    ``disputed`` names attributes several rows declare *differently* — the same name as an integer on
    one type and a string on another. Colouring by one is still possible and still global, and it
    would put two meanings on one scale; a reader can only weigh that if told, and leaving such a name
    out of ``shared`` without saying why makes it look like one that simply is not shared.
    """

    shared: list[SharedAttributeOfferResponse]
    disputed: list[str]
    types: list[TypeOfferResponse]
    #: How many model entities the diagram places, whatever their types declare.
    #:
    #: Dropping the attribute-less rows made two very different states identical to a reader of
    #: `types` alone: a diagram that draws no model entities, and one that draws thirteen whose types
    #: declare no attributes. A surface with only `types` told a reader the second was the first,
    #: which was untrue of a diagram full of processes and services.
    drawn: int
    #: Whether a legend for this diagram would say anything at all — whether it uses any notation
    #: there is to explain. A surface offers the control only when this is true, because a legend
    #: checkbox that produces nothing is indistinguishable from one that failed.
    can_explain_notation: bool

"""Response contracts for the GSN surface: the drafted argument, its rendering, its publications.

Derived from ``verification/case_draft.draft_gsn_from_records`` and ``assurance_gsn.build_gsn_draft``.
The scaffold is *drafted*, never asserted: every node in it is derived from store content by a stated
rule, which is why each carries the ids it was derived from. An argument a reader cannot trace back to
the hazards and constraints behind it is not an assurance case.

``publishable`` is the load-bearing field. A GSN diagram leaves the confidential store, so it may be
published only when the effective classification of everything it argues over permits it — and it is
``false`` whenever the reader's own view was filtered, because a case drawn from a partial graph would
argue from evidence the author cannot see.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from src.infrastructure.gui.contracts.assurance_analyses import AssuranceAnalysisRecord


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GsnNodeRef(_Closed):
    """A store node named in a gap: enough to render the row and open it."""

    node_id: str
    name: str


class GsnTopGoal(_Closed):
    """The overall claim, derived from the losses the analysis identified.

    ``source_losses`` is empty when the analysis has none — the goal still exists, stated generically,
    because an argument has to have a top claim even before its losses are written down.
    """

    node_id: str
    gsn_type: Literal["goal"]
    claim: str
    source_losses: list[str]


class GsnSubGoal(_Closed):
    """One claim per hazard: that the hazard is controlled."""

    node_id: str
    gsn_type: Literal["goal"]
    claim: str
    source_hazard: str
    leads_to_losses: list[str]


class GsnStrategy(_Closed):
    """How a sub-goal is argued: by constraint derivation from the STPA unsafe control actions.

    ``uca_ids`` and ``constraint_ids`` are the derivation itself, published so a reader can check that
    the strategy rests on the chain it claims to.
    """

    node_id: str
    gsn_type: Literal["strategy"]
    description: str
    source_hazard: str
    uca_ids: list[str]
    constraint_ids: list[str]


class GsnSolution(_Closed):
    """One piece of evidence discharging a constraint."""

    node_id: str
    gsn_type: Literal["solution"]
    description: str
    constraint_id: str
    evidence_id: str


class GsnGaps(_Closed):
    """What the argument does not yet cover: the two ways it can be incomplete.

    Kept apart rather than summed. A constraint with no evidence is an argument that asserts something
    unsupported; a hazard with no constraint is one that does not argue about it at all. The second is
    the more serious, and a single count would hide which it was.
    """

    constraints_without_evidence: list[GsnNodeRef]
    hazards_without_constraints: list[GsnNodeRef]


class GsnDraft(_Closed):
    """The scaffold: a top claim, a sub-goal per hazard, a strategy each, and the evidence found."""

    top_goal: GsnTopGoal
    sub_goals: list[GsnSubGoal]
    strategies: list[GsnStrategy]
    solutions: list[GsnSolution]
    gaps: GsnGaps


class GsnDiagramNode(_Closed):
    """One node of the drawable graph, carrying the store ids it was derived from."""

    node_id: str
    name: str
    gsn_type: str
    source_assurance_ids: list[str]


class GsnDiagramEdge(_Closed):
    """One edge of the drawable graph, in the GSN relation vocabulary."""

    source_id: str
    target_id: str
    conn_type: Literal["supported-by", "in-context-of"]


class GsnDiagramEntities(_Closed):
    """The draft as a graph, ready for the renderer. A projection of the draft, not a second source."""

    nodes: list[GsnDiagramNode]
    edges: list[GsnDiagramEdge]


class GsnCompletenessCheck(_Closed):
    """One argument-completeness check: whether it passed, and what it found if not.

    ``gap_count`` accompanies ``gaps`` because a caller rendering a summary needs the number without
    walking the list, and the two coming from one place is what keeps them agreeing.
    """

    passed: bool
    gap_count: int
    gaps: list[GsnNodeRef]


class GsnCompleteness(_Closed):
    """The three checks, keyed by name, with a sentence a person can read.

    An open map with a closed value: the check set belongs to the argument rules, so adding a check
    should not mean editing a delivery DTO.
    """

    passed: bool
    checks: dict[str, GsnCompletenessCheck]
    summary: str


class GsnDraftResponse(_Closed):
    """The drafted argument for one analysis, with whether it may leave the store.

    ``effective_tlp`` is the classification of the argument as a whole — the most sensitive thing it
    reasons over, not the analysis's own label — and ``publishable`` is derived from it. It is forced
    ``false`` when the reader's view was filtered: a case drawn from a partial graph would argue from
    evidence its own author cannot see, and publishing that is worse than not publishing.

    ``classification_order`` travels along so a client can rank the value it was given without holding
    a second copy of an ordered vocabulary.
    """

    analysis: AssuranceAnalysisRecord
    draft: GsnDraft
    diagram_entities: GsnDiagramEntities
    effective_tlp: str
    publishable: bool
    classification_order: list[str]
    visibility_limited: bool


class GsnRenderedResponse(GsnDraftResponse):
    """The draft, plus the drawn diagram and whatever the renderer complained about.

    ``warnings`` is the renderer's, not the argument's: a layout the renderer could not honour is a
    different concern from a gap in the case, and folding them together would let a cosmetic
    complaint read as an assurance finding.
    """

    svg: str
    warnings: list[str]


class GsnPublicationRecordedResponse(_Closed):
    """What a publication recorded: the diagram, and how many source bindings were written.

    ``binding_count`` is what was *written*, not what was sent. A binding naming a node that does not
    exist is skipped rather than failing the publication, so the two numbers can differ — and the one
    worth reporting is the one that will be there when someone follows the diagram back.
    """

    status: Literal["published"]
    diagram_id: str
    binding_count: int

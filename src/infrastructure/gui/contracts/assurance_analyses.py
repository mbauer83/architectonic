"""Response contracts for the assurance analysis aggregate: the collection, the detail read, the writes.

The analysis is the aggregate root for a unit of STPA/CAST/GRC/FMEA work, and every one of these
bodies is a projection of the one record the store now returns — canonical across all four backends
(``assurance/_analysis_records.ANALYSIS_RECORD_FIELDS``). That guarantee is what makes closing these
possible at all: before it, the record's key set depended on which store the deployment ran, so a
contract closed against one answered 500 on another.

``method`` and ``status`` are the domain's own vocabularies at type level, so a method the domain
retires cannot go on being published here. ``tlp`` is deliberately a plain string: nothing validates
it on the way in (``assurance_analysis.create_analysis`` checks name, method and status only, and
``is_above_ceiling`` reads an unrecognised value as the least sensitive), so declaring a closed set
would document a guarantee the write path does not make.

Every read here is exposure-filtered before the counts are taken. A total counted before filtering
would disclose the existence of what the ceiling withholds, through a number nobody thinks of as
content; ``visibility_limited`` is how a reader learns their view is partial without learning by how
much.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from src.domain.assurance.assurance_analysis import AnalysisMethod, AnalysisStatus


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssuranceAnalysisRecord(_Closed):
    """One analysis, as every backend now hands it back.

    ``group_id`` is filing and is null until someone files it — present-and-null rather than absent,
    because "not filed" is an answer and a missing key is not. ``architecture_anchor_id`` is empty
    when the analysis spans several systems rather than naming one: the binding then lives on its
    individual nodes' architecture references.
    """

    analysis_id: str
    group_id: str | None
    name: str
    method: AnalysisMethod
    architecture_anchor_id: str
    status: AnalysisStatus
    tlp: str
    created_at: str
    updated_at: str


class AssuranceAnalysisListResponse(_Closed):
    """The analyses this reader may see, and whether that is all of them.

    ``count`` is the length of ``analyses`` rather than the store's total — the same number, said
    twice, and deliberately so: the handler has always sent it, and a client that renders a count
    beside a list must not have to choose between two sources for it. What it is *not* is the
    unfiltered population, which is why the withheld cardinality appears nowhere.
    """

    analyses: list[AssuranceAnalysisRecord]
    count: int
    visibility_limited: bool


class AssuranceAnalysisSummary(_Closed):
    """An analysis named just enough to show beside something it owns or uses.

    Mirrors ``assurance_provenance.analysis_summary`` field for field — the five it selects, and no
    more. The rest of the record is deliberately absent: this appears next to a *node*, where a reader
    needs to know whose work they are looking at, not when the analysis was last touched.
    """

    analysis_id: str
    name: str
    method: AnalysisMethod
    status: AnalysisStatus
    group_id: str | None


class AssuranceGroupRecord(_Closed):
    """One filing group: a name, a description, and when it was made.

    No classification of its own, which is what distinguishes a group from the analyses it holds —
    the store's ceiling governs those, so there is nothing on this record to filter and the group
    list is returned as stored.
    """

    group_id: str
    name: str
    description: str
    created_at: str
    updated_at: str


class AssuranceGroupListResponse(_Closed):
    """Every group, in the order a reader expects to file into them (by name)."""

    groups: list[AssuranceGroupRecord]


class AssuranceParticipatingNodesResponse(_Closed):
    """The nodes an analysis draws on without having authored them.

    Ids rather than records: a caller who wants the nodes themselves wants the working-set page
    (``GET /analyses/{id}/nodes``), which states each item's relationship. This answers the narrower
    question — which participations does this analysis hold — and answering it with whole nodes would
    duplicate that collection at a second address.

    ``count`` is the length of the filtered list, so it agrees with what the reader can see rather
    than with what is stored.
    """

    analysis_id: str
    participating_node_ids: list[str]
    count: int
    visibility_limited: bool


class AssuranceAnalysisDetailResponse(_Closed):
    """One analysis with the size of its authored contents, as far as this reader may see.

    ``node_count`` counts the analysis's own nodes after exposure filtering, so it agrees with the
    node list the reader then opens rather than with the store.
    """

    analysis: AssuranceAnalysisRecord
    node_count: int


class AssuranceGuidanceResponse(_Closed):
    """Method coaching for one topic: what it is, why it matters, how to do it, and what says so.

    Static content, so this route is callable with the store locked — there is nothing confidential in
    an explanation of what a hazard is, and a wizard that could not explain its own step until the
    store was unlocked would be useless exactly when a newcomer needs it.

    The three trailing fields are prose a particular topic adds and the others do not: an FMEA reader
    arriving from a spreadsheet tradition needs to be told what is deliberately absent
    (``if_you_already_know_fmea``), and the two priority notes exist because the commonest way to
    misuse an action-priority band is to treat it as permission to skip a constraint. Optional here
    because they are per-topic, not because they are unreliable.
    """

    topic: str
    step: str
    what: str
    why: str
    how: str
    standards: list[str]
    if_you_already_know_fmea: str | None = None
    priority_never_overrides_a_constraint: str | None = None
    targeting_signals_are_not_factors: str | None = None

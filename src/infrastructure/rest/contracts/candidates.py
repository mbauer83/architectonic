"""Candidate architecture records, scoped comparisons and stress-analysis projections."""
from pydantic import Field, JsonValue, model_serializer

from src.infrastructure.rest.contracts.diagram_layout_editing import DiagramLayoutGeometryResponse
from src.infrastructure.rest.contracts.wire_nulls import NullsOmitted
from src.infrastructure.rest.contracts.wire_shape import Closed

type Fields = dict[str, JsonValue]


class CandidateCreate(Closed):
    record: Fields
    diagram: str | None = None


class CandidateEdit(Closed):
    based_on: str
    patch: Fields


class CandidateOperation(Closed):
    """An edit to record among a candidate's operations; the server reads its base."""

    based_on: str
    operation: Fields


class CandidateResponse(Closed):
    record: Fields
    version: str


class CandidateRebase(Closed):
    """Re-base a candidate's drifted operations on the model as it stands now."""

    based_on: str


class AnalysisStart(Closed):
    """Start a stress analysis: the document and its naive architecture, in one write."""

    title: str = Field(min_length=1)
    question: str | None = None
    naive: Fields = Field(description="The naive architecture's record: a name, and its scope or parent.")
    scope_diagram: str | None = Field(
        None, description="The diagram the analysis is drawn on; its entities scope a naive that states none.",
    )


class AnalysisStarted(Closed):
    document: str
    naive_candidate: CandidateResponse


class CandidateSummary(Closed):
    id: str
    name: str
    state: str
    parent: str | None


class CandidateList(Closed):
    candidates: list[CandidateSummary]


class ScopedEntity(NullsOmitted):
    id: str
    fields: Fields
    artifact_id: str | None = Field(None, description="The id chosen for an entity the stack creates.")


class ConnectionKey(NullsOmitted):
    source_entity: str
    connection_type: str
    target_entity: str


class ScopedConnection(ConnectionKey):
    fields: Fields


class ScopedView(NullsOmitted):
    entities: list[ScopedEntity]
    connections: list[ScopedConnection]


class ChangedField(NullsOmitted):
    before: JsonValue
    after: JsonValue

    @model_serializer(mode="wrap")
    def _include_both_values(self, serialize):
        # An absent side of a change is meaningful. Keep both keys even for null-omitting canvas geometry.
        return {**serialize(self), "before": self.before, "after": self.after}


class ChangeDifference(NullsOmitted):
    kind: str
    target: str | ConnectionKey
    change: str
    fields: dict[str, ChangedField]


class OperationStanding(NullsOmitted):
    operation: Fields
    standing: str
    reason: str


class CandidateStanding(NullsOmitted):
    candidate: str
    standing: list[OperationStanding]


class CandidateComparison(CandidateStanding):
    base: str
    stack: list[str]
    view: ScopedView
    diff: list[ChangeDifference]
    drawing: DiagramLayoutGeometryResponse | None = None


class CandidateSelection(Closed):
    candidates: list[str] = Field(min_length=1)


class OverlapParty(Closed):
    set_id: str
    operation: Fields


class CandidateOverlap(Closed):
    kind: str
    subject: str
    parties: list[OverlapParty]


class IntegrationCheck(CandidateSelection):
    overlaps: list[CandidateOverlap]


class IncompleteCell(Closed):
    table: str
    row: str
    column: str


class AnalysisOutstanding(Closed):
    unwalked: list[str]
    without_end_state: list[str]
    without_required_behaviour: list[str]
    without_adaptation: list[str]
    unexplained_hits: list[str]
    incomplete_rows: list[IncompleteCell]


class UntouchedElement(Closed):
    id: str
    fan_in: int
    fan_out: int


class CoverageHints(Closed):
    by_kind: dict[str, int]
    unused_kinds: list[str]
    single_stressor_end_states: list[str]
    untouched: list[UntouchedElement]


class AnalysisProgress(Closed):
    document: str
    naive_candidate: str
    progress: AnalysisOutstanding
    coverage: CoverageHints


class CouplingPair(Closed):
    left: str
    right: str
    count: int


class AnalysisIncidence(Closed):
    document: str
    naive_candidate: str
    stressors: list[Fields]
    end_states: list[Fields]
    adaptations: list[Fields]
    incidence: list[Fields]
    coupling: list[CouplingPair]

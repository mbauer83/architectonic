"""Candidate architecture records, scoped comparisons and stress-analysis projections."""
from pydantic import Field, JsonValue

from src.infrastructure.rest.contracts.diagram_layout_editing import DiagramLayoutGeometryResponse
from src.infrastructure.rest.contracts.wire_shape import Closed

type Fields = dict[str, JsonValue]


class CandidateCreate(Closed):
    record: Fields
    diagram: str | None = None


class CandidateEdit(Closed):
    based_on: str
    patch: Fields


class CandidateResponse(Closed):
    record: Fields
    version: str


class CandidateSummary(Closed):
    id: str
    name: str
    state: str
    parent: str | None


class CandidateList(Closed):
    candidates: list[CandidateSummary]


class ScopedEntity(Closed):
    id: str
    fields: Fields


class ConnectionKey(Closed):
    source_entity: str
    connection_type: str
    target_entity: str


class ScopedConnection(ConnectionKey):
    fields: Fields


class ScopedView(Closed):
    entities: list[ScopedEntity]
    connections: list[ScopedConnection]


class ChangedField(Closed):
    before: JsonValue
    after: JsonValue


class ChangeDifference(Closed):
    kind: str
    target: str | ConnectionKey
    change: str
    fields: dict[str, ChangedField]


class OperationStanding(Closed):
    operation: Fields
    standing: str
    reason: str


class CandidateStanding(Closed):
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

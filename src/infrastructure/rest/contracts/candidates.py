"""Candidate architecture records, scoped comparisons and stress-analysis projections."""
from pydantic import Field, JsonValue, model_serializer

from src.infrastructure.candidate_wire import CandidateHeader, CandidatePatch, RecordedEdit
from src.infrastructure.rest.contracts.diagram_layout_editing import DiagramLayoutGeometryResponse
from src.infrastructure.rest.contracts.wire_nulls import NullsOmitted
from src.infrastructure.rest.contracts.wire_shape import Closed

type Fields = dict[str, JsonValue]


class CandidateCreate(Closed):
    """A new candidate: its header, optionally scoped by a diagram, optionally with edits recorded in it."""

    record: CandidateHeader
    diagram: str | None = Field(
        None, description="A stored diagram whose entities become the scope. Exclusive with `record.scope`.",
    )
    operations: list[RecordedEdit] = Field(
        default_factory=list, description="Edits recorded in order, as `POST …/operations` records them.",
    )


class CandidateEdit(Closed):
    """Header fields to change, over the version last read."""

    based_on: str = Field(description="The `version` the last read or write of this candidate answered.")
    patch: CandidatePatch


class CandidateOperations(Closed):
    """Edits to record among a candidate's operations, in order, as one write; the server reads each base."""

    based_on: str = Field(description="The `version` the last read or write of this candidate answered.")
    operations: list[RecordedEdit] = Field(
        min_length=1,
        description=(
            "Applied in order, each over the ones before. An edit of a field replaces an earlier edit of it, "
            "an edit back to the value beneath drops it, and `drop` takes back what the candidate records "
            "about one thing. Refused (409) unless the candidate is a draft."
        ),
    )


class CandidateResponse(Closed):
    record: Fields
    version: str


class CandidateDeletion(Closed):
    """What deleting a candidate does: on a dry run, what it would."""

    candidate: str
    dry_run: bool
    deleted: bool
    version: str = Field(description="The version the deletion was checked against.")


class CandidateRebase(Closed):
    """Re-base a candidate's drifted operations on the model as it stands now."""

    based_on: str


class AnalysisStart(Closed):
    """Start a stress analysis: the document and its naive architecture, in one write."""

    title: str = Field(min_length=1)
    question: str | None = None
    naive: CandidateHeader = Field(description="The naive architecture's header: a name, and its scope or parent.")
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
    scope: list[str] = Field(description="The model's entities it is read over, by id; empty when started empty.")
    operations: int = Field(description="How many operations it records itself, not counting what it stacks on.")


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
    by_kind: dict[str, int] = Field(description="Design stressors by kind, each kind as written; only kinds in use.")
    unwritten_perspectives: list[str] = Field(
        description="Perspectives no design stressor is written from, by id; empty while no stressor names a kind.",
    )
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


class CandidateApply(Closed):
    """Write a candidate's operations onto the model; a dry run answers what would be written."""

    dry_run: bool = True


class CandidateApplication(NullsOmitted):
    candidate: str
    dry_run: bool
    integrated: bool = Field(description="Whether the operations were written and the candidate integrated.")
    refusal: str | None = Field(None, description="Why the candidate cannot be applied, in the refusing rule's words.")
    operation_id: str | None = Field(None, description="The write's operation, when one ran.")
    standing: list[OperationStanding] = Field(
        description="Each operation's standing; those already there are skipped, the rest are written.",
    )

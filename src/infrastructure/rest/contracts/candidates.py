"""Candidate architecture records, scoped comparisons and stress-analysis projections."""
from pydantic import Field, JsonValue, model_serializer

from src.infrastructure.candidate_wire import CandidateHeader, CandidatePatch, IntegrationResolution, RecordedEdit
from src.infrastructure.rest.contracts.diagram_layout_editing import DiagramLayoutGeometryResponse
from src.infrastructure.rest.contracts.path_components import PathComponent
from src.infrastructure.rest.contracts.wire_nulls import NullsOmitted
from src.infrastructure.rest.contracts.wire_shape import Closed

type Fields = dict[str, JsonValue]


class CandidateCreate(Closed):
    """A new candidate: its header, optionally with edits recorded in it."""

    record: CandidateHeader
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
    context: str | None = Field(
        None, description="The environment, and the decision the evaluation informs; free text.",
    )
    naive: CandidateHeader = Field(
        description="The architecture under evaluation: a name, and its scope, the diagram it is drawn on, or the "
        "candidate it stacks on.",
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
    diagram: str | None = Field(description="The stored diagram it names to be drawn on; null where it names none.")
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


class ScopeDrawingRequest(Closed):
    """A scope that no stored diagram draws, to be drawn as a generated view before a candidate holds it."""

    scope: list[str] = Field(min_length=1, description="The model's entities in the scope, by id in either spelling.")
    name: str = Field(min_length=1, description="What the generated view is called.")


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


class TargetStateIds(NullsOmitted):
    """Where a candidate applied as a target state stands in the model, by the ids the application wrote."""

    baseline: str = Field(description="The Baseline plateau.")
    target: str = Field(description="The Target plateau.")
    gap: str = Field(description="The «gap» assessment associated with both plateaus.")
    copies: dict[str, str] = Field(description="Each changed element's id, to its \"(target)\" copy's.")
    added: dict[str, str] = Field(description="Each element the candidate adds, by its alias, to its id.")


class CandidateTargetStateApplication(NullsOmitted):
    """What applying a candidate as a target state writes beside the baseline, or why it would not."""

    candidate: str
    dry_run: bool
    applied: bool = Field(description="Whether the target state was written and recorded on the candidate.")
    refusal: str | None = Field(None, description="Why the candidate cannot be applied, in the refusing rule's words.")
    operation_id: str | None = Field(None, description="The write's operation, when one ran.")
    standing: list[OperationStanding] = Field(description="Each of the candidate's own operations' standing.")
    target_state: TargetStateIds | None = Field(None, description="Where it stands, or would, once written.")
    operations: list[Fields] = Field(default_factory=list, description="The generated operations, as written.")
    unheld: list[str] = Field(
        default_factory=list, description="Types of elements a plateau may not aggregate, left unheld.",
    )


class CandidateMove(NullsOmitted):
    """What moving a target state into the baseline writes, or why it would not."""

    candidate: str
    dry_run: bool
    integrated: bool = Field(description="Whether the move was written and the candidate integrated.")
    refusal: str | None = Field(None, description="Why the move is refused, in the refusing rule's words.")
    operation_id: str | None = Field(None, description="The write's operation, when one ran.")
    standing: list[OperationStanding] = Field(description="Each generated operation's standing.")
    operations: list[Fields] = Field(default_factory=list, description="The generated operations.")


class CandidateWithdrawal(NullsOmitted):
    """What withdrawing a target state removes from the model, or why it would not."""

    candidate: str
    dry_run: bool
    released: bool = Field(
        False, description="Whether the target state was taken out and the candidate released as a draft.",
    )
    refusal: str | None = Field(
        None, description="Why the withdrawal is refused: what was written since that refers to the target state.",
    )
    operation_id: str | None = Field(None, description="The write's operation, when one ran.")
    operations: list[Fields] = Field(default_factory=list, description="The generated removals.")


class CandidateDiagramSave(Closed):
    """Store the view a candidate drawn on no stored diagram is generated as, and draw the candidate on it."""

    based_on: str = Field(description="The `version` the last read or write of this candidate answered.")
    name: str | None = Field(None, min_length=1, description="The new diagram's name; the candidate's own when absent.")
    group: PathComponent | None = Field(
        None, description="The collection the diagram is filed in; uncategorized when absent.",
    )
    dry_run: bool = True


class CandidateDiagramSaved(NullsOmitted):
    candidate: str
    dry_run: bool
    diagram: str | None = Field(None, description="The diagram written; absent on a dry run.")
    name: str
    entities: int = Field(description="How many of the model's entities the diagram draws.")
    relations: int = Field(description="How many relations among them it draws.")
    version: str | None = Field(None, description="The candidate's version once it names the diagram.")


class CandidateIntegrate(Closed):
    """Candidates to integrate into a new draft, and how each conflict between them is settled."""

    candidates: list[str] = Field(min_length=2, description="Distinct drafts or offered candidates on one parent.")
    name: str = Field(min_length=1, description="The integration's name.")
    rationale: str = ""
    resolutions: list[IntegrationResolution] = Field(default_factory=list)
    dry_run: bool = True


class IntegrationConflict(NullsOmitted):
    kind: str
    subject: str
    parties: list[OverlapParty]
    actions: list[str] = Field(description="What this conflict permits: take, drop, and merge where a value is set.")


class CandidateIntegration(NullsOmitted):
    candidates: list[str]
    dry_run: bool
    operations: int = Field(description="How many operations the integration holds, or would once settled.")
    conflicts: list[IntegrationConflict] = Field(description="The conflicts still standing after the resolutions.")
    integration: CandidateResponse | None = Field(None, description="The new candidate, once written.")

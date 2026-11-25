"""What the candidate-architecture and stress-analysis tools say about themselves.

Kept beside the tools rather than in their docstrings because they carry what an agent needs to call a
tool correctly the first time — argument shapes, refusals, versions, dry runs — and that runs past one
line. Each REST route says the same in its own words; the operation is one.
"""

VERSIONED = (
    "`based_on` is the `version` the last read or write of the candidate answered; a candidate changed since "
    "is refused, and the refusal names the current version."
)

CHANGE_SET_LIST = "List candidate architectures: id, name, state, parent, scope and how many operations each records."

CHANGE_SET_READ = (
    "Read one candidate architecture: its record (header and the operations it records, each with the base "
    "it was written against) and its `version`, which every edit of it states as `based_on`. artifact_id "
    "takes either spelling of the id."
)

CHANGE_SET_STANDING = (
    "How each of a candidate's own operations stands against the model as it is now: `applies`, "
    "`already-there` (skipped by an apply), `drifted` (what it replaces changed since it was written; "
    "change_set_rebase writes it again) or `conflicting` (nothing to apply to; the reason says what), each "
    "with a sentence saying what to do."
)

CHANGE_SET_COMPARE = (
    "Compare a candidate, composed with every candidate it stacks on, against a base: the composed view of "
    "the scoped entities and connections, the differences field by field, and each operation's standing. "
    "base: `model` (the default), `naive` (with `naive` naming the analysis's naive candidate), or another "
    "candidate's id outside this one's descendants. `drawing` is the geometry the comparison is drawn on: "
    "the stored diagram named by diagram, else the one the candidate's stack is drawn on, else a view "
    "generated from the scoped entities and the relations among them; absent for a candidate with none."
)

CHANGE_SET_RESIDUALITY = (
    "A candidate's residuality in every stress analysis that judged it or integrated it: per analysis, its "
    "verdict counts beside the naive's, and R = (Y − X) / n once both are judged on every usable test "
    "stressor."
)

CHANGE_SET_CHECK = (
    "Check drafts or offered candidates for integration conflicts: every claim two of them (or the "
    "candidates they stack on) make on the same thing, with the operations of each party. Reads only."
)

CHANGE_SET_CREATE = (
    "Create a candidate architecture. record: its header — name (required), id (minted if omitted), "
    "rationale, state (draft or candidate), parent (a candidate to stack on), scope (entity ids it is read "
    "over), diagram (the stored diagram it is drawn on; with no scope, its entities become the scope), "
    "answers, satisfies. operations: edits recorded in it in the same write, as change_set_record takes "
    "them. Answers the record and its version."
)

CHANGE_SET_RECORD = (
    "Record edits among a draft candidate's operations, in order, as one write; the server reads each edit's "
    "base from what the candidate stacks on, so no base is stated. An edit: create_entity (fields with "
    "artifact_type, name, group; artifact_id minted when omitted), edit_entity (artifact_id, field, value, "
    "key for a keyed field), remove_entity, add_connection / edit_connection / remove_connection "
    "(source_entity, connection_type, target_entity), and drop (takes back what the candidate records about "
    "an entity or a connection, or one field of it). An edit of a field replaces an earlier one; an edit "
    "back to the value beneath drops it. Ids in either spelling. " + VERSIONED
)

CHANGE_SET_EDIT = (
    "Change header fields of a candidate: name, rationale, parent, scope, answers, satisfies, and state — "
    "draft <-> candidate, either -> rejected or superseded; integrated only by change_set_apply; terminal "
    "states never change. `changes` restores an operation list exactly as a read answered it (an undo); to "
    "change operations, use change_set_record. " + VERSIONED
)

CHANGE_SET_REBASE = (
    "Write a draft candidate's drifted operations again against the model as it is now, keeping the value "
    "each asks for: applying it then overwrites deliberately what the model came to say. Nothing drifted, "
    "nothing changes. A conflicting operation is left for its author to drop. " + VERSIONED
)

CHANGE_SET_APPLY = (
    "Write a draft or offered candidate's operations onto the model in one transaction, all or none, and "
    "mark it integrated. Refused while an operation conflicts or has drifted, or a candidate it stacks on is "
    "not integrated; operations already in the model are skipped. dry_run (default true) answers what would "
    "be written and the refusal, if any, instead of raising it. operation_id is for artifact_get_operation."
)

CHANGE_SET_DELETE = (
    "Delete a candidate nothing refers to. Refused while a candidate stacks on it, an analysis starts from "
    "it, an analysis's verdicts or adaptations name it, or it is integrated (kept as the record of what was "
    "written). dry_run (default true) answers the plan; based_on, when given, refuses a candidate changed "
    "since it was read."
)

ANALYSIS_START = (
    "Start a stress analysis: its naive candidate and the stress-analysis document naming it, both or "
    "neither. naive: the naive's header as change_set_create takes it (name; scope, diagram or parent): it "
    "owns the scope and the diagram the analysis is drawn on. context: optional free text, the environment "
    "and the decision the evaluation informs. "
    "Stressors, end states, incidence, adaptations and verdicts are then rows of the document's tables, "
    "written with artifact_edit_document_table."
)

ANALYSIS_PROGRESS = (
    "What is unfinished in a stress analysis (stressors not walked, without end state, end states without "
    "required behaviour or adaptation, hits without a note) and coverage hints: design stressors by kind, "
    "the perspectives (analysis_perspectives) none is written from, and scoped elements no stressor hits."
)

ANALYSIS_INCIDENCE = (
    "A stress analysis's design stressors with the elements each hits (and those it names that the naive "
    "does not hold), its end states, adaptations, incidence rows, and how often each pair of elements is hit "
    "together."
)

ANALYSIS_TEST_SET = (
    "A stress analysis's test set: its stressors, the verdicts, each judged or integrated architecture's "
    "residuality (Y − X) / n beside the naive, and the procedure's stage."
)

ANALYSIS_PERSPECTIVES = (
    "The perspectives offered for writing stressors (PESTLE, five forces, business model canvas, "
    "organisation, and any the repository adds in .arch-repo/stress-perspectives.json), each with an id, "
    "its kind and a guiding question."
)

ANALYSIS_HOLD_OUT = (
    "Move a third of a stress analysis's design stressors into its test set, drawn at random from seed. "
    "Without a seed the draw is the analysis's own, so a dry run (the default) previews exactly what the "
    "write then moves; the seed is answered either way. Asked again once the test set holds that draw, it "
    "answers it as done and moves nothing; a different draw over a held test set is refused. Fewer than "
    "three design stressors is refused."
)

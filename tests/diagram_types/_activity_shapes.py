"""The shapes the activity notation permits, as fixtures this repository owns.

One catalogue, shared by every activity test, because the gate is stated over *what the notation
permits* rather than over the shape that broke. Four of these were found broken by rendering them,
not by reading the walk: a cyclic graph drew nothing at all, two disconnected chains drew only the
first, a fork converging on a plain action drew its whole tail twice, and a decision whose arms
converge with no declared merge edge dropped the else arm.

The reported diagram is not in this repository and is not copied in — `cross_level_convergence`
reproduces its *shape* with ids and labels of our own.

No label may be a substring of another label in the same shape: `step_count` matches emitted step
lines by label, so overlapping labels would count each other.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.diagram_types.activity.renderer import ActivityPumlRenderer
from src.domain.repository.frontmatter import parse_frontmatter

_REPO = Path(__file__).resolve().parents[2] / "engagements" / "ENG-ARCH-REPO" / "architecture-repository"


def flow(source: str, target: str) -> dict[str, object]:
    return {"conn_type": "step-flow", "source": source, "target": target}


def then(decision: str, first: str) -> dict[str, object]:
    return {"conn_type": "step-then", "source": decision, "target": first}


def otherwise(decision: str, first: str) -> dict[str, object]:
    return {"conn_type": "step-else", "source": decision, "target": first}


def branch(fork: str, first: str) -> dict[str, object]:
    return {"conn_type": "step-fork-branch", "source": fork, "target": first}


def in_lane(step: str, lane: str) -> dict[str, object]:
    return {"conn_type": "step-in-lane", "source": step, "target": lane}


def actions(**labels: str) -> list[dict[str, object]]:
    return [{"id": step_id, "label": label} for step_id, label in labels.items()]


def decision(step_id: str, condition: str, then_label: str = "yes", else_label: str = "no") -> dict[str, object]:
    return {"id": step_id, "condition": condition, "then_label": then_label, "else_label": else_label}


@dataclass(frozen=True)
class ActivityShape:
    """One declared step graph, with what it is here to exercise."""

    name: str
    exercises: str
    entities: dict[str, object]
    connections: list[dict[str, object]] = field(default_factory=list)

    def render(self) -> str:
        return ActivityPumlRenderer({}).render_body(
            self.name, [], [], "activity", _REPO,
            diagram_entities=self.entities,
            diagram_connections=self.connections,
        )


def step_count(body: str, label: str) -> int:
    """How many times the body draws a step with this label.

    Counted over emitted step lines rather than raw text: a label is wrapped in the selection
    sentinel (`:[[arch://id label]];`), so a bare substring search would also match a note or a
    link elsewhere in the body.
    """
    return sum(1 for line in body.splitlines() if line.startswith(":") and label in line)


BOTH_ARMS_CONVERGE = ActivityShape(
    name="both arms converge",
    exercises="Arms of one decision flowing to the same step, with no declared merge edge.",
    entities={
        "action": actions(select="choose what to lift", write="write it"),
        "decision": [decision("keyed", "are both ends typed")],
    },
    connections=[then("keyed", "select"), otherwise("keyed", "select"), flow("select", "write")],
)

ARMS_CONVERGE_DOWNSTREAM = ActivityShape(
    name="arms converge downstream",
    exercises="Arms meeting one step further on, with no declared merge edge.",
    entities={
        "action": actions(prepare="prepare the change", reject="record the refusal",
                          settle="reconcile both outcomes", publish="publish the result"),
        "decision": [decision("valid", "does it pass")],
    },
    connections=[
        then("valid", "prepare"), otherwise("valid", "reject"),
        flow("prepare", "settle"), flow("reject", "settle"), flow("settle", "publish"),
    ],
)

MERGE_EQUALS_A_BRANCH_TARGET = ActivityShape(
    name="merge equals a branch target",
    exercises="A declared merge edge pointing at the then-arm's own first step.",
    entities={
        "action": actions(settle="apply it", dispute="raise an objection", wrap="close the request"),
        "decision": [decision("agreed", "is it agreed")],
    },
    connections=[
        then("agreed", "settle"), otherwise("agreed", "dispute"), flow("agreed", "settle"),
        flow("settle", "wrap"),
    ],
)

FORK_CONVERGES_ON_AN_ACTION = ActivityShape(
    name="fork converges on an action",
    exercises="Parallel branches meeting at a plain action, with no join entry in fork[].",
    entities={
        "action": actions(measure="measure it", sample="sample it",
                          compare="compare the two", report="report the finding"),
        "fork": [{"id": "split"}],
    },
    connections=[
        branch("split", "measure"), branch("split", "sample"),
        flow("measure", "compare"), flow("sample", "compare"), flow("compare", "report"),
    ],
)

A_STEP_GRAPH_THAT_LOOPS = ActivityShape(
    name="a step graph that loops",
    exercises="A retry loop — a back edge from a branch to a step already emitted.",
    entities={
        "action": actions(attempt="attempt the write", wait="back off", accept="accept it"),
        "decision": [decision("ok", "did it succeed")],
    },
    connections=[flow("attempt", "ok"), then("ok", "accept"), otherwise("ok", "wait"), flow("wait", "attempt")],
)

A_LOOP_DECLARED_FROM_ITS_MIDDLE = ActivityShape(
    name="a loop declared from its middle",
    exercises=(
        "The same retry loop with its branch targets declared first. Where the walk starts is then "
        "a choice rather than a fact, and taking the first declared step draws the loop from inside "
        "one of its branches."
    ),
    entities={
        "action": actions(accept="accept it", wait="back off", attempt="attempt the write"),
        "decision": [decision("ok", "did it succeed")],
    },
    connections=[flow("attempt", "ok"), then("ok", "accept"), otherwise("ok", "wait"), flow("wait", "attempt")],
)

A_LOOP_WHOSE_BODY_HOLDS_A_DECISION = ActivityShape(
    name="a loop whose body holds a decision",
    exercises=(
        "The ordinary retry shape: a loop whose body branches. Refused until the acceptance "
        "criterion described the region the emitter walks rather than a single-successor chain. "
        "Lanes are declared and the whole cycle sits in one of them, which is what keeps the way "
        "back off the steps it returns past."
    ),
    entities={
        "action": actions(receive="receive the request", attempt="attempt the write",
                          repair="repair the input", ignore="carry on regardless",
                          wait="back off", accept="accept it"),
        "decision": [decision("recoverable", "can it be repaired"),
                     decision("ok", "did it succeed")],
        "swimlane": [{"id": "lane_caller", "label": "Caller"},
                     {"id": "lane_service", "label": "Service"}],
    },
    connections=[
        flow("receive", "attempt"), flow("attempt", "recoverable"),
        then("recoverable", "repair"), otherwise("recoverable", "ignore"),
        flow("recoverable", "ok"),
        then("ok", "accept"), otherwise("ok", "wait"), flow("wait", "attempt"),
        in_lane("receive", "lane_caller"), in_lane("accept", "lane_caller"),
        *[in_lane(step, "lane_service")
          for step in ("attempt", "recoverable", "repair", "ignore", "ok", "wait")],
    ],
)

A_FORK_INSIDE_A_LOOP_BODY = ActivityShape(
    name="a fork inside a loop body",
    exercises=(
        "The body of a loop is walked as a region, so it may hold any structured construct and not "
        "only a decision. Kept because the criterion was widened to allow it, and a shape the "
        "product newly draws needs its picture checked as much as one it always drew."
    ),
    entities={
        "action": actions(attempt="attempt the write", measure="measure the result",
                          sample="sample the log", wait="back off", accept="accept it"),
        "decision": [decision("ok", "did it succeed")],
        "fork": [{"id": "split"}],
        "swimlane": [{"id": "lane_caller", "label": "Caller"},
                     {"id": "lane_service", "label": "Service"}],
    },
    connections=[
        branch("split", "measure"), branch("split", "sample"),
        flow("attempt", "split"), flow("measure", "ok"), flow("sample", "ok"),
        then("ok", "accept"), otherwise("ok", "wait"), flow("wait", "attempt"),
        in_lane("accept", "lane_caller"),
        *[in_lane(step, "lane_service")
          for step in ("attempt", "split", "measure", "sample", "ok", "wait")],
    ],
)

TWO_DISCONNECTED_CHAINS = ActivityShape(
    name="two disconnected chains",
    exercises="Two chains with no edge between them — both are declared, so both are drawn.",
    entities={"action": actions(draft="draft it", review="review it", archive="archive it", purge="purge it")},
    connections=[flow("draft", "review"), flow("archive", "purge")],
)

CROSS_LEVEL_CONVERGENCE = ActivityShape(
    name="cross level convergence",
    exercises=(
        "One step arrived at from two different nesting depths, neither arrival dominating: the "
        "outer decision's else-arm and an inner decision's then-arm. No structured placement in an "
        "if/else tree covers exactly those two paths."
    ),
    entities={
        "action": actions(inspect="inspect the pair", revise="revise the link",
                          select="choose what to lift", preflight="report what would happen",
                          write="write it in one transaction"),
        "decision": [decision("keyed", "are both ends typed"), decision("permitted", "is the pair permitted")],
    },
    connections=[
        then("keyed", "inspect"), otherwise("keyed", "select"),
        flow("inspect", "permitted"),
        then("permitted", "select"), otherwise("permitted", "revise"), flow("permitted", "preflight"),
        flow("preflight", "write"),
    ],
)

CROSS_LEVEL_CONVERGENCE_ACROSS_LANES = ActivityShape(
    name="cross level convergence across lanes",
    exercises="The same cross-level arrival, with the two arrival points in different swimlanes.",
    entities={
        **CROSS_LEVEL_CONVERGENCE.entities,
        "swimlane": [{"id": "author", "label": "You"}, {"id": "tool", "label": "Architectonic"}],
    },
    connections=[
        *CROSS_LEVEL_CONVERGENCE.connections,
        in_lane("keyed", "tool"), in_lane("inspect", "tool"), in_lane("permitted", "tool"),
        in_lane("revise", "author"), in_lane("select", "author"),
        in_lane("preflight", "tool"), in_lane("write", "tool"),
    ],
)

A_JOIN_REACHED_INSIDE_A_DECISION = ActivityShape(
    name="a join reached inside a decision",
    exercises="The reported minimal repro: a fork whose branch reaches its join inside a decision.",
    entities={
        "action": actions(assess="assess the request", bypass="skip it",
                          notify="notify the requester", close="close the request"),
        "decision": [decision("needed", "is it needed")],
        "fork": [{"id": "split"}, {"id": "rejoin"}],
    },
    connections=[
        branch("split", "needed"), then("needed", "assess"), otherwise("needed", "bypass"),
        flow("assess", "rejoin"), flow("rejoin", "notify"), flow("notify", "close"),
    ],
)

NESTED_DECISIONS_PAST_A_JOIN = ActivityShape(
    name="nested decisions past a join",
    exercises=(
        "The reported diagram's shape: a fork whose single branch is the outermost of three nested "
        "decisions, each carrying its own merge edge, the join reached at the innermost then-target, "
        "and a three-step tail past the join."
    ),
    entities={
        "action": actions(escalate="escalate it", annotate="annotate it", defer="defer it",
                          stamp="stamp the record", log="log the outcome", finish="finish the case",
                          notify="notify the requester", archive="archive the record",
                          purge="purge the working copy"),
        "decision": [decision("urgent", "is it urgent"), decision("priced", "is it priced"),
                     decision("stocked", "is it stocked")],
        "fork": [{"id": "split"}, {"id": "rejoin"}],
    },
    connections=[
        branch("split", "urgent"),
        then("urgent", "priced"), otherwise("urgent", "escalate"), flow("urgent", "finish"),
        then("priced", "stocked"), otherwise("priced", "annotate"), flow("priced", "log"),
        then("stocked", "rejoin"), otherwise("stocked", "defer"), flow("stocked", "stamp"),
        flow("rejoin", "notify"), flow("notify", "archive"), flow("archive", "purge"),
    ],
)

A_JOIN_REACHED_INSIDE_A_NESTED_FORK = ActivityShape(
    name="a join reached inside a nested fork",
    exercises=(
        "A fork inside a decision arm, its single branch reaching the join within a further "
        "decision. What follows the join belongs inside that arm, past `end fork` — appending it to "
        "the end of the body would land it outside the arm that leads to it."
    ),
    entities={
        "action": actions(refuse="refuse the request", amend="amend the paperwork",
                          dispatch="dispatch it", confirm="confirm receipt",
                          close="close the file"),
        "decision": [decision("approved", "is it approved"), decision("checked", "does it check out")],
        "fork": [{"id": "split"}, {"id": "rejoin"}],
    },
    connections=[
        then("approved", "split"), otherwise("approved", "refuse"), flow("approved", "close"),
        branch("split", "checked"),
        then("checked", "rejoin"), otherwise("checked", "amend"),
        flow("rejoin", "dispatch"), flow("dispatch", "confirm"),
    ],
)

ONE_FORK = ActivityShape(
    name="one fork",
    exercises="start -> fork -> (a | b | c) -> join -> tail1 -> tail2.",
    entities={
        "action": actions(begin="begin", first="branch a", second="branch b", third="branch c",
                          tail_one="after join", tail_two="and then"),
        "fork": [{"id": "split"}, {"id": "rejoin"}],
    },
    connections=[
        flow("begin", "split"),
        branch("split", "first"), branch("split", "second"), branch("split", "third"),
        flow("first", "rejoin"), flow("second", "rejoin"), flow("third", "rejoin"),
        flow("rejoin", "tail_one"), flow("tail_one", "tail_two"),
    ],
)

NESTED_FORKS = ActivityShape(
    name="nested forks",
    exercises="The shape that multiplied the tail: an outer fork of two, one branch holding a fork of three.",
    entities={
        "action": actions(begin="begin", meta_one="meta one", meta_two="meta two",
                          inner_x="inner x", inner_y="inner y", inner_z="inner z",
                          tail_one="after join", tail_two="and then"),
        "fork": [{"id": "outer"}, {"id": "outer_join"}, {"id": "inner"}, {"id": "inner_join"}],
    },
    connections=[
        flow("begin", "outer"),
        branch("outer", "meta_one"), branch("outer", "inner"),
        flow("meta_one", "outer_join"),
        branch("inner", "inner_x"), branch("inner", "inner_y"), branch("inner", "inner_z"),
        flow("inner_x", "inner_join"), flow("inner_y", "inner_join"), flow("inner_z", "inner_join"),
        flow("inner_join", "meta_two"), flow("meta_two", "outer_join"),
        flow("outer_join", "tail_one"), flow("tail_one", "tail_two"),
    ],
)

A_BRANCH_THAT_NEVER_REACHES_THE_JOIN = ActivityShape(
    name="a branch that never reaches the join",
    exercises="A branch may end on its own — the fork still closes and the continuation is drawn once.",
    entities=ONE_FORK.entities,
    connections=[c for c in ONE_FORK.connections
                 if not (c["conn_type"] == "step-flow" and c["source"] == "third")],
)

A_PARTITION_AROUND_A_DECISION = ActivityShape(
    name="a partition around a decision",
    exercises="A partition holding a decision whose arms converge — the stop must not escape the box.",
    entities={
        "action": actions(gather="gather the inputs", skip="skip the step",
                          reconcile="reconcile them", hand_off="hand it on"),
        "decision": [decision("ready", "is it ready")],
        "partition": [{"id": "intake", "label": "Intake"}],
    },
    connections=[
        {"conn_type": "step-contains", "source": "intake", "target": "ready"},
        then("ready", "gather"), otherwise("ready", "skip"),
        flow("gather", "reconcile"), flow("skip", "reconcile"),
        flow("intake", "hand_off"),
    ],
)

CATALOGUE: tuple[ActivityShape, ...] = (
    BOTH_ARMS_CONVERGE,
    ARMS_CONVERGE_DOWNSTREAM,
    MERGE_EQUALS_A_BRANCH_TARGET,
    FORK_CONVERGES_ON_AN_ACTION,
    A_STEP_GRAPH_THAT_LOOPS,
    A_LOOP_DECLARED_FROM_ITS_MIDDLE,
    A_LOOP_WHOSE_BODY_HOLDS_A_DECISION,
    A_FORK_INSIDE_A_LOOP_BODY,
    TWO_DISCONNECTED_CHAINS,
    CROSS_LEVEL_CONVERGENCE,
    CROSS_LEVEL_CONVERGENCE_ACROSS_LANES,
    A_JOIN_REACHED_INSIDE_A_DECISION,
    NESTED_DECISIONS_PAST_A_JOIN,
    A_JOIN_REACHED_INSIDE_A_NESTED_FORK,
    ONE_FORK,
    NESTED_FORKS,
    A_BRANCH_THAT_NEVER_REACHES_THE_JOIN,
    A_PARTITION_AROUND_A_DECISION,
)


def bundled_shapes() -> list[ActivityShape]:
    """Both bundled activity diagrams, rendered from their own declared entities and connections.

    The frontmatter is read through its one owner (`src.domain.repository.frontmatter`) rather than
    spelled here a second time.
    """
    shapes: list[ActivityShape] = []
    for path in sorted(_REPO.glob("diagram-catalog/diagrams/*/ACT@*.puml")):
        fm = parse_frontmatter(path.read_text(encoding="utf-8"))
        entities = fm.get("diagram-entities")
        connections = fm.get("connections")
        assert isinstance(entities, dict) and isinstance(connections, list), path
        shapes.append(ActivityShape(
            name=str(fm.get("name") or path.stem),
            exercises=f"the bundled diagram {path.name}",
            entities=entities,
            connections=[c for c in connections if isinstance(c, dict)],
        ))
    return shapes

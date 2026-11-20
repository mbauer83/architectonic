"""What a diagram's stated layout and its groupings' identities get wrong (E370–E373, W375–W379).

Errors, because the file says something that cannot be acted on and its author can always put right:

* **E370** — the ``layout`` block cannot be read; the message is the reader's own sentence.
* **E371** — a layout entry names an instance, grouping or relation the diagram does not hold. The
  write path never stores one (it drops them with the member an edit removes), so this is a hand
  edit or a merge.
* **E372** — a layout on a diagram that cannot carry one: a ``manual-layout`` diagram, whose body is
  kept verbatim, or a type that holds its own records.
* **E373** — ``authored-groupings`` is not what a grouping may say: no id (a diagram from before
  groupings had identities, with what to run), a repeated id, a rule that is not one, both a rule and
  a list.

Warnings, because each can arise without anybody editing the diagram and none stops it being read:

* **W375** — a rule key no element of the diagram satisfies. Whether a rule has members is the
  model's to say, and may change back.
* **W376** — a relation that does not leave its element straight outward by one stub (I1).
* **W377** — a relation routed through one of its own ends (I2).
* **W378** — two connected elements over each other, which no route can join.
* **W379** — a box over an element that is not inside it, which the box hides.

The four geometry rules are warnings for the reason the rendered-picture rules are, turned around:
an element that is placed but not sized is as large as its label makes it, so renaming an element
elsewhere moves a border under a stated route. A write refused for that would be a write refused
over a change its author did not make. They are decided only over elements whose size the block
states; a size the renderer chose is not known here, and silence is not evidence.

One finding per kind per diagram, naming the first few places and counting the rest.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from src.application.modeling.diagram_identities import diagram_identities, drawn_instances, occurrences_stated
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult
from src.domain.artifact_id import canonical_entity_key
from src.domain.diagrams.authored_groupings import (
    GROUPING_ID_KEY,
    RuleKey,
    check_groupings,
    read_rule_key,
    states_a_ruled_grouping,
)
from src.domain.diagrams.grouping_membership import DrawingTraits, place_in_groupings
from src.domain.diagrams.layout.layout_block import LAYOUT_KEY, Layout, MalformedLayout, read_layout
from src.domain.diagrams.layout.layout_checks import (
    LayoutDefect,
    check_layout_geometry,
    entries_naming_nothing,
    placed_extent,
)

_NAMED_IN_MESSAGE = 3

_CODE_OF: Mapping[LayoutDefect, str] = {
    LayoutDefect.END_NOT_LEAVING_OUTWARD: "W376",
    LayoutDefect.ROUTE_THROUGH_OWN_END: "W377",
    LayoutDefect.CONNECTED_ELEMENTS_OVERLAP: "W378",
    LayoutDefect.BOX_HIDES_ELEMENT: "W379",
}


def _strings(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _listed(places: Sequence[str]) -> str:
    rest = len(places) - _NAMED_IN_MESSAGE
    return "; ".join(places[:_NAMED_IN_MESSAGE]) + (f"; and {rest} more" if rest > 0 else "")


def check_groupings_are_identified(fm: Mapping[str, object], result: VerificationResult, loc: str) -> None:
    """E373 for everything ``authored-groupings`` says that a grouping may not."""
    result.issues.extend(
        Issue(Severity.ERROR, "E373", problem, loc) for problem in check_groupings(fm.get("authored-groupings"))
    )


def _traits(
    fm: Mapping[str, object], registry: ArtifactRegistry, domain_of_type: Callable[[str], str]
) -> DrawingTraits[str]:
    """Domain and type of each instance: an occurrence has its backing entity's."""
    backing = dict(occurrences_stated(fm.get("diagram-entities"), fm.get("bindings")))

    def type_of(instance: str) -> str:
        record = registry.get_entity(backing.get(instance, instance))
        return record.artifact_type if record is not None else ""

    return DrawingTraits[str](domain_of=lambda instance: domain_of_type(type_of(instance)), type_of=type_of)


def _members_by_box(
    fm: Mapping[str, object], layout: Layout, instances: Sequence[str], traits: DrawingTraits[str]
) -> dict[str, frozenset[str]]:
    """Who is inside each box the layout sizes: a stated grouping's members, or what a rule key admits."""
    groupings = fm.get("authored-groupings")
    if check_groupings(groupings):
        return {}  # E373 says what is wrong with them; who is in a grouping that is not one is not asked
    held = set(instances)
    placement = place_in_groupings(
        groupings,
        drawings=instances,
        named=lambda name: key if (key := canonical_entity_key(name)) in held else None,
        traits=traits,
    )
    members = {
        str(placed.declaration.get(GROUPING_ID_KEY)): frozenset(placed.every_member())
        for placed in placement.every_grouping()
    }
    for key in layout.boxes:
        if key not in members and not states_a_ruled_grouping(groupings):
            try:
                path = read_rule_key(key).path
            except ValueError:
                continue
            admitted = frozenset(
                instance for instance in placement.unclaimed if all(traits.admits(rule, instance) for rule in path)
            )
            if admitted:  # a rule nothing satisfies draws no box, and a box not drawn hides nothing
                members[key] = admitted
    return members


def check_layout(
    fm: Mapping[str, object],
    registry: ArtifactRegistry,
    result: VerificationResult,
    loc: str,
    *,
    domain_of_type: Callable[[str], str],
    holds_its_own_records: bool,
) -> None:
    """Every layout finding for one diagram's frontmatter."""
    if LAYOUT_KEY not in fm:
        return
    try:
        layout = read_layout(fm[LAYOUT_KEY])
    except MalformedLayout as refusal:
        result.issues.append(Issue(Severity.ERROR, "E370", str(refusal), loc))
        return
    if fm.get("manual-layout") is True or holds_its_own_records:
        reason = (
            "it is manual-layout, and its hand-written body is kept verbatim" if fm.get("manual-layout") is True
            else "its diagram type holds its own records and is arranged by its own generator"
        )
        result.issues.append(
            Issue(Severity.ERROR, "E372", f"This diagram states a layout and cannot carry one: {reason}.", loc)
        )
        return

    traits = _traits(fm, registry, domain_of_type)
    entity_ids = _strings(fm.get("entity-ids-used"))
    instances = drawn_instances(entity_ids, fm.get("diagram-entities"), fm.get("bindings"))
    ruled = states_a_ruled_grouping(fm.get("authored-groupings"))

    def rule_admits(key: RuleKey) -> bool:
        """A rule draws a box only while no grouping is ruled and some element satisfies its whole path."""
        return not ruled and any(all(traits.admits(rule, instance) for rule in key.path) for instance in instances)

    identities = diagram_identities(
        entity_ids_used=entity_ids, connection_ids_used=_strings(fm.get("connection-ids-used")),
        diagram_entities=fm.get("diagram-entities"), diagram_connections=fm.get("connections"),
        authored_groupings=fm.get("authored-groupings"), bindings=fm.get("bindings"), rule_admits=rule_admits,
    )
    dangling = entries_naming_nothing(layout, identities)
    named = [
        *(f"element {key}" for key in dangling.elements), *(f"box {key}" for key in dangling.boxes),
        *(f"relation {key}" for key in dangling.relations), *(f"stacked entry {key}" for key in dangling.stacked),
    ]
    if named:
        result.issues.append(Issue(
            Severity.ERROR, "E371",
            f"The layout names what this diagram does not hold, {len(named)} time(s): {_listed(named)}.", loc,
            details={"entries": named},
        ))
    if dangling.rules:
        result.issues.append(Issue(
            Severity.WARNING, "W375",
            "The layout addresses a box by a rule no element of this diagram satisfies: "
            f"{_listed(list(dangling.rules))}.",
            loc, details={"rules": list(dangling.rules)},
        ))

    extents = {
        key: extent for key, placed in layout.elements.items()
        if key in identities.instances and (extent := placed_extent(placed)) is not None
    }
    findings = check_layout_geometry(
        layout, extents=extents, relations=identities.relations,
        members_of_box=_members_by_box(fm, layout, sorted(identities.instances), traits),
    )
    for defect in LayoutDefect:
        places = [" · ".join(finding.subjects) for finding in findings if finding.defect is defect]
        if places:
            result.issues.append(Issue(
                Severity.WARNING, _CODE_OF[defect],
                f"The layout has {defect.value}, {len(places)} time(s): {_listed(places)}.", loc,
                details={"places": places},
            ))

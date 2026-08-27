"""The sentinel link an activity step carries — written onto a line, and read back off one.

Both directions live here because they are one syntax. The renderer writes a step's identity into
the rendered line so the viewer can resolve a shape back to its artifact; the verifier reads it back
to tell whether a declared step is drawn at all. A second reading of it is a defect, and
`tests/architecture/test_each_syntax_has_one_reader.py` carries the row that says so.

Extracted from ``renderer.py`` to keep it under the project's LoC limit.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.infrastructure.rendering.puml_text_escaping import puml_line_text

_SENTINEL_START = "[[arch://"

#: The step kinds whose emission carries a sentinel — so the only ones whose presence in a body can
#: be read back. `fork` is absent because PlantUML's `fork` keyword takes no label or link argument
#: at all, so a fork and a join are drawn as bare bars with nothing on them to read.
LABELLED_STEP_KINDS = ("action", "decision", "partition")


def puml_text(value: str) -> str:
    """*value*, safe on an activity line — the shared line escaping plus this notation's own rule.

    `|` bounds a swimlane header, so a label carrying one would close the header early and leave the
    rest as body text. Replaced rather than escaped: PlantUML offers no escape for it there.

    Beside the sentinel because both are what this notation does to a label before writing it, and
    because `lane_header` needs it — `_emission` used to own it and imports this module, so leaving it
    there would have made the pair circular.
    """
    return puml_line_text(value).replace("|", "/")


def _link_clause(url: str) -> str:
    return f"[[{url.replace(']', '%5D')}]]"


def sentinel_target(step: dict[str, Any]) -> str:
    """The bound entity id if this step maps to one, else the step's own local id."""
    entity_id = step.get("entity_id")
    return str(entity_id) if entity_id else str(step.get("id") or "")


def sentinel_wrapped(step: dict[str, Any], label: str) -> str:
    """*label* wrapped in this step's sentinel ``arch://`` link — ``[[arch://id label]]``.

    The label text itself becomes the anchor: the viewer extension resolves the rendered
    element back to its artifact from the ``<a href="arch://…">``, and with the preamble's
    plain-text hyperlink skinparams the label looks like ordinary text — no separate visible
    ``arch://…`` link text inside the shape (which is what the old standalone-clause emission
    produced). Steps without a sentinel render the label unchanged.
    """
    sentinel = sentinel_target(step)
    if not sentinel:
        return label
    return f"[[arch://{sentinel.replace(']', '%5D')} {label.replace(']', '%5D')}]]"


def user_link_suffix(step: dict[str, Any]) -> str:
    """The user's own ``link`` (if any) as a separate, deliberately visible link clause."""
    link = step.get("link")
    return f" {_link_clause(str(link))}" if link else ""


def link_suffix(step: dict[str, Any]) -> str:
    """User link plus standalone sentinel clause — the partition-title form.

    ``partition "label" [[url]] {`` attaches the link to the partition title without
    rendering separate link text, so partitions keep this emission; actions and decisions
    use `sentinel_wrapped` on their label instead.
    """
    clauses: list[str] = []
    link = step.get("link")
    if link:
        clauses.append(_link_clause(str(link)))
    sentinel = sentinel_target(step)
    if sentinel:
        clauses.append(_link_clause(f"arch://{sentinel}"))
    return f" {' '.join(clauses)}" if clauses else ""


def lane_header(lane: dict[str, Any]) -> str:
    """One swimlane header, carrying the lane's identity — ``|[[arch://id Label]]|``.

    A lane may be bound, and the binding persisted while the header stayed a bare `|Label|`: an
    action, a decision and a partition were all selectable and the lane alone was not, in this same
    module. The notation permits it — verified on the pinned PlantUML, where such a header renders one
    anchor and keeps its visible text — so a lane is not the case `fork` is, whose keyword accepts no
    link at all.

    Here rather than in either caller because both spelled it: the renderer wrote the first lane's
    header and the emission walk wrote every switch after it. Wiring one and not the other would have
    left the first lane as the only unclickable one.

    `puml_text` runs on the label before the link wraps it, and that order matters: `|` delimits the
    header, so a label carrying one has to be replaced before it can end the header early.
    """
    label = puml_text(str(lane.get("label") or lane.get("id") or ""))
    return f"|{sentinel_wrapped(lane, label)}|"


def sentinel_of(line: str) -> str | None:
    """The step a rendered line stands for, or None where the line carries no sentinel.

    One reading serves both emission forms. `sentinel_wrapped` puts the label after the sentinel, so
    the id ends at the space before it; `link_suffix` emits the sentinel as a clause of its own, so
    the id ends at the closing bracket. Whichever comes first is the end of the id, and `]` inside
    it was escaped on the way out.
    """
    at = line.find(_SENTINEL_START)
    if at < 0:
        return None
    rest = line[at + len(_SENTINEL_START):]
    ends = [where for where in (rest.find(" "), rest.find("]")) if where >= 0]
    sentinel = rest[:min(ends)] if ends else rest
    return sentinel.replace("%5D", "]") or None


def _is_lane_header(line: str) -> bool:
    """Whether this line is a swimlane header rather than a step.

    A header is the only construct bounded by `|` on both sides, and `puml_text` has already replaced
    any `|` a label carried — so the delimiters cannot be anything but the header's own.
    """
    stripped = line.strip()
    return len(stripped) > 1 and stripped.startswith("|") and stripped.endswith("|")


def drawn_step_counts(body: str) -> Mapping[str, int]:
    """How many times the body draws each **step**, read off the sentinel each drawn line carries.

    Counts rather than presence, because the two answer different questions and only one of them was
    being asked. W045 asks whether a declared step is drawn *at all*; nothing asked whether it is drawn
    more often than the model gives it ways in — and a partition reached from three decision arms is
    inlined three times, so a three-step block became nine drawn steps with nothing reporting it.

    Lane headers are excluded, and the exclusion is the point: since a bound lane became selectable it
    carries a sentinel too, and counting a lane as a step would make the step question unanswerable.
    Read apart here rather than by each caller, because one syntax gets one reader.
    """
    counts: dict[str, int] = {}
    for line in body.splitlines():
        if _is_lane_header(line):
            continue
        sentinel = sentinel_of(line)
        if sentinel:
            counts[sentinel] = counts.get(sentinel, 0) + 1
    return counts


def drawn_step_ids(body: str) -> frozenset[str]:
    """Every **step** the body draws.

    A step drawn once and reached from elsewhere by a connector appears once: the connector line
    carries no sentinel of its own, only the line that draws the step does.

    Derived from `drawn_step_counts` so the sentinel reading has one implementation; a caller asking
    "is it drawn" and one asking "how often" must not be able to disagree.
    """
    return frozenset(drawn_step_counts(body))


def drawn_lane_ids(body: str) -> frozenset[str]:
    """Every swimlane the body draws, read off its header's sentinel.

    The other half of the same syntax. A lane's header is emitted once per switch *into* it, so a
    diagram that returns to a lane repeats the header — hence a set, not a count.
    """
    return frozenset(
        sentinel
        for line in body.splitlines()
        if _is_lane_header(line)
        for sentinel in (sentinel_of(line),)
        if sentinel
    )

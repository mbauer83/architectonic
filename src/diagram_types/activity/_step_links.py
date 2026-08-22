"""The sentinel link an activity step carries — written onto a line, and read back off one.

Both directions live here because they are one syntax. The renderer writes a step's identity into
the rendered line so the viewer can resolve a shape back to its artifact; the verifier reads it back
to tell whether a declared step is drawn at all. A second reading of it is a defect, and
`tests/architecture/test_each_syntax_has_one_reader.py` carries the row that says so.

Extracted from ``renderer.py`` to keep it under the project's LoC limit.
"""

from __future__ import annotations

from typing import Any

_SENTINEL_START = "[[arch://"

#: The step kinds whose emission carries a sentinel — so the only ones whose presence in a body can
#: be read back. `fork` is absent because PlantUML's `fork` keyword takes no label or link argument
#: at all, so a fork and a join are drawn as bare bars with nothing on them to read.
LABELLED_STEP_KINDS = ("action", "decision", "partition")


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


def drawn_step_ids(body: str) -> frozenset[str]:
    """Every step the body draws, read off the sentinel each drawn line carries.

    A step drawn once and reached from elsewhere by a connector appears once: the connector line
    carries no sentinel of its own, only the line that draws the step does.
    """
    return frozenset(
        sentinel for sentinel in (sentinel_of(line) for line in body.splitlines()) if sentinel
    )

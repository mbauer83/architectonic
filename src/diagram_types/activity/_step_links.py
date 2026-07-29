"""User-supplied + sentinel PlantUML link emission for activity steps.

Extracted from ``renderer.py`` to keep it under the project's LoC limit.
"""

from __future__ import annotations

from typing import Any


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

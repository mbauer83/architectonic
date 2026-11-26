"""The revision of what a whole-diagram replacement replaces, and the refusal of one made over a stale read.

A replacement (`PUT /api/diagrams/{id}`, MCP `artifact_replace_diagram`) writes a diagram whole from what its
caller read, so two sessions saving the same diagram silently kept the later one. The caller now sends the
revision it read (`base_revision`), and a replacement over anything else is refused, naming what changed.

What the revision covers is what a replacement would overwrite unseen: what the diagram draws, its other
statements, and its body. Not its `layout` block, whose entries a replacement patches with a `based_on` each
(`layout_patch`) — so arranging on the canvas, which writes only the layout, does not make the session's own
next save stale — and not `last-updated`, which every write restamps. Each of the three parts has its own
digest (`record_revision`, the revision of a record by its field values), so a refusal can say which changed.
"""

from __future__ import annotations

from src.application.change_sets.base import record_revision
from src.domain.diagrams.layout.layout_block import LAYOUT_KEY
from src.domain.repository.frontmatter import body_after_frontmatter, parse_frontmatter

#: What the diagram draws: the statements a composition carries.
_DRAWN_KEYS = frozenset({
    "entity-ids-used", "connection-ids-used", "diagram-entities", "connections", "authored-groupings", "bindings",
    "edge-labels",
})
#: Written by every write, or revised per entry by the write itself.
_UNREVISED_KEYS = frozenset({LAYOUT_KEY, "last-updated"})
#: The parts, in the order the revision spells them, by what a refusal calls each.
_PARTS = ("what it draws", "its name, status and other statements", "its PlantUML body")
_SEPARATOR = "-"


def replaced_revision(source: str) -> str:
    """The revision a reader of the diagram file *source* sends back with a replacement.

    Read from the file's text, through the one frontmatter reader, so the diagram read and the write that
    checks it cannot come to parse the same file differently.
    """
    frontmatter, body = parse_frontmatter(source), body_after_frontmatter(source)
    drawn = {key: value for key, value in frontmatter.items() if key in _DRAWN_KEYS}
    stated = {key: value for key, value in frontmatter.items() if key not in _DRAWN_KEYS | _UNREVISED_KEYS}
    return _SEPARATOR.join(record_revision(part) for part in (drawn, stated, {"body": body}))


class DiagramChanged(ValueError):
    """A replacement over a revision the diagram no longer has; nothing is written."""

    def __init__(self, artifact_id: str, *, read: str, current: str, last_updated: object) -> None:
        self.current = current
        was, now = read.split(_SEPARATOR), current.split(_SEPARATOR)
        changed = [part for index, part in enumerate(_PARTS) if index >= len(was) or was[index] != now[index]]
        when = f" (last updated {last_updated})" if last_updated else ""
        super().__init__(
            f"Diagram '{artifact_id}' changed since it was read{when}: {', '.join(changed)}. Nothing was written. "
            f"Read it again — its revision is now {current} — and save over that."
        )


def refuse_a_stale_replacement(artifact_id: str, *, read: str, source: str) -> None:
    """Raise `DiagramChanged` where the stored diagram, whose file is *source*, is no longer at the revision *read*."""
    if (current := replaced_revision(source)) != read:
        last_updated = parse_frontmatter(source).get("last-updated")
        raise DiagramChanged(artifact_id, read=read, current=current, last_updated=last_updated)

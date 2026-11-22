"""A change to part of a diagram's layout: entries set or removed, each optionally checked against what it replaces.

```json
{
  "elements": {"APP@1712870400.xVrBYD": {"value": {"x": 320, "y": 200}, "based_on": {"x": 300, "y": 200}}},
  "boxes": {"rule:domain=business": null},
  "relations": {"<drawn-relation key>": {"value": null}},
  "z": {"g-7Fq2aB": {"value": 2, "based_on": null}}
}
```

Each section is keyed as the layout block keys it. An entry is ``null`` (remove it) or an object with
``value`` — what the entry becomes, ``null`` to remove it — and, optionally, ``based_on``: what the
caller read it as, ``null`` for absent. Where ``based_on`` is given and the layout no longer holds
that, the entry is a conflict and nothing is applied: an editor that read a layout before someone
else changed it is told which entries moved under it, rather than silently undoing the other change.

Values are read and written by the layout block's own reader and writer (`read_layout`,
`layout_as_written`), never a second time here: an entry is held in the spelling the block writes, so
a patch can state exactly what a block can, and two spellings of one value compare equal.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from src.domain.diagrams.layout.layout_block import Layout, MalformedLayout, layout_as_written, read_layout

SECTIONS: tuple[str, ...] = ("elements", "boxes", "relations", "z")

#: A value any section accepts, to learn the canonical spelling of a key whose entry is removed.
_PLACEHOLDER: Mapping[str, object] = {"elements": {"x": 0, "y": 0}, "boxes": {"x": 0, "y": 0}, "relations": {}, "z": 0}

type Written = object


@dataclass(frozen=True)
class EntryChange:
    """One entry: what it becomes as the block writes it (None removes it); what it was read as, if checked."""

    value: Written | None
    checked: bool = False
    based_on: Written | None = None


@dataclass(frozen=True)
class LayoutPatch:
    """Changes to a layout, each by the section and canonical key the layout block uses."""

    sections: Mapping[str, Mapping[str, EntryChange]] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not any(self.sections.values())


class LayoutConflict(ValueError):
    """Entries whose ``based_on`` is not what the layout holds, by section and key."""

    def __init__(self, entries: tuple[tuple[str, str], ...]) -> None:
        self.entries = entries
        named = ", ".join(f"{section} {key}" for section, key in entries)
        super().__init__(f"The layout changed under these entries since they were read: {named}.")


def _written_entry(section: str, key: str, value: object, where: str) -> tuple[str, Written]:
    """*key* in its canonical spelling and *value* as the block writes it, both through the block's reader."""
    try:
        written = layout_as_written(read_layout({section: {key: value}}))
    except MalformedLayout as refusal:
        raise MalformedLayout(f"{where}: {refusal}") from refusal
    entries = written.get(section)
    if not isinstance(entries, Mapping) or len(entries) != 1:
        # A relation stated as {} writes nothing: the router decides all of it, as for an absent entry.
        return key, {}
    ((canonical, entry),) = entries.items()
    return str(canonical), entry


def _entry(section: str, key: str, raw: object, where: str) -> tuple[str, EntryChange]:
    canonical, _ = _written_entry(section, key, _PLACEHOLDER[section], where)
    if raw is None:
        return canonical, EntryChange(None)
    if not isinstance(raw, Mapping) or "value" not in raw or not set(raw) <= {"value", "based_on"}:
        raise MalformedLayout(f"{where} is {raw!r}; an entry is null, or {{value, based_on?}}.")
    value = None if raw["value"] is None else _written_entry(section, key, raw["value"], f"{where}.value")[1]
    if "based_on" not in raw:
        return canonical, EntryChange(value)
    was = raw["based_on"]
    based_on = None if was is None else _written_entry(section, key, was, f"{where}.based_on")[1]
    return canonical, EntryChange(value, checked=True, based_on=based_on)


def read_layout_patch(raw: object) -> LayoutPatch:
    """The patch *raw* states. Refuses, with a sentence saying what and where, one that is not a patch."""
    if not isinstance(raw, Mapping):
        raise MalformedLayout(f"A layout patch is a mapping of sections; got {raw!r}.")
    unknown = sorted(str(key) for key in raw if key not in SECTIONS)
    if unknown:
        raise MalformedLayout(f"A layout patch states {', '.join(unknown)}; it holds only {', '.join(SECTIONS)}.")

    def section(name: str, entries: object) -> dict[str, EntryChange]:
        if not isinstance(entries, Mapping):
            raise MalformedLayout(f"patch.{name} is {entries!r}; expected a mapping of entries.")
        return dict(_entry(name, str(key), value, f"patch.{name}.{key}") for key, value in entries.items())

    return LayoutPatch({str(name): section(str(name), entries) for name, entries in raw.items()})


def _held(written: Mapping[str, object], section: str) -> Mapping[str, object]:
    entries = written.get(section)
    return entries if isinstance(entries, Mapping) else {}


def patched(layout: Layout, patch: LayoutPatch, *, stored: Layout | None = None) -> Layout:
    """*layout* with *patch* applied. Raises `LayoutConflict`, applying nothing, where an entry moved under it.

    *stored* is what a reader could have read, where that is not *layout* itself: a diagram with no
    layout is patched over its first layout, but a reader read it as stating nothing, and its
    ``based_on`` is checked against that.
    """
    written = layout_as_written(layout)
    read = written if stored is None else layout_as_written(stored)
    conflicts = tuple(
        (section, key)
        for section, entries in patch.sections.items()
        for key, change in entries.items()
        if change.checked and _held(read, section).get(key) != change.based_on
    )
    if conflicts:
        raise LayoutConflict(conflicts)

    def applied(section: str) -> dict[str, object]:
        changes = patch.sections.get(section, {})
        kept = {key: value for key, value in _held(written, section).items() if key not in changes}
        return kept | {key: change.value for key, change in changes.items() if change.value is not None}

    grid = {"grid": layout.grid} if layout.grid is not None else {}
    return read_layout(grid | {section: applied(section) for section in SECTIONS})

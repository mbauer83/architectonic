"""Reading a ``specialization`` frontmatter / connection-metadata value as the ordered set
it now is. A concept may carry several specializations (ArchiMate §15.2); the on-disk value
is a bare scalar (every existing repo — one element, no migration) or a list.

One reader so every consumer — the verifier, rendering, styling, promotion — interprets the
value identically and cannot drift from the writer.
"""

from __future__ import annotations

from collections.abc import Sequence


def applied_specialization_slugs(raw: object) -> tuple[str, ...]:
    """The applied specialization slugs from a raw ``specialization`` value. A scalar reads
    as a one-element set; a list reads in order, de-duplicated, with blanks dropped; anything
    else is no specialization."""
    if isinstance(raw, str):
        return (raw,) if raw else ()
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        seen: dict[str, None] = {}
        for item in raw:
            if isinstance(item, str) and item and item not in seen:
                seen[item] = None
        return tuple(seen)
    return ()

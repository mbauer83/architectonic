"""A reference to something that does not exist yet: the alias form `$ref:<alias>`.

A batch that creates an entity and then connects it has to name the entity before the repository has
allocated its id. The creating item states an alias, and everything else in the batch that means that
entity writes the alias behind this prefix. Whatever applies the batch replaces each one with the id
the create was given.

The form is written by whoever plans a batch and read by whoever applies one, so it is written and
read here and nowhere else. It was spelled in three readers and four writers before this module
existed, and a change set — whose operations name each other the same way — would have been the
eighth.

It sits in the domain because both a plan (application) and an applier (infrastructure) need it, and
it knows nothing but a string.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

#: What marks a reference as provisional. Private: the form is this module's to spell.
_PREFIX = "$ref:"
#: Where an alias written in running text ends: at anything an alias does not hold.
_ALIAS_ENDS = r"(?![A-Za-z0-9_.-]*[A-Za-z0-9_-])"


def provisional(alias: str) -> str:
    """The reference that means "whatever the create called *alias* becomes"."""
    return f"{_PREFIX}{alias}"


def alias_of(reference: str) -> str | None:
    """The alias a provisional reference carries, or None where *reference* is already an id."""
    return reference[len(_PREFIX) :] if reference.startswith(_PREFIX) else None


def name_in(reference: str) -> str:
    """What *reference* says once the form is taken off: its alias, or the id it already was."""
    alias = alias_of(reference)
    return reference if alias is None else alias


def named_in_text(text: str, names: Mapping[str, str]) -> str:
    """*text* with each provisional reference to an alias in *names* written as the name *names* gives it.

    For a sentence about operations that name what they create by alias — a standing's reason, say — read
    by someone who knows the entity by the id chosen for it. One pass, the longest reference first, so a
    reference is never rewritten inside a longer one that begins with it.
    """
    if not names:
        return text
    references = sorted((provisional(alias) for alias in names), key=len, reverse=True)
    pattern = re.compile(f"(?:{'|'.join(re.escape(reference) for reference in references)}){_ALIAS_ENDS}")
    return pattern.sub(lambda found: names[found.group(0)[len(_PREFIX) :]], text)

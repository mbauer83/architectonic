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

#: What marks a reference as provisional. Private: the form is this module's to spell.
_PREFIX = "$ref:"


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

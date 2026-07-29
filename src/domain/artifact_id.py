"""Canonical identity helpers for artifact IDs.

Format: PREFIX@epoch.random[.slug]
  - PREFIX  = 2–6 uppercase alpha
  - epoch   = unix timestamp digits
  - random  = short alphanumeric key (may include hyphens)
  - slug    = optional kebab-case label (rename-volatile)

Short form (no slug) is the stable identity key throughout the index.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: The rename-volatile slug tail. Defined once: anything that needs to recognise a slug
#: must use this rather than restate the charset, or the two grammars drift apart and the
#: looser one silently matches text that is not part of an id.
SLUG_PATTERN = r"[A-Za-z0-9][A-Za-z0-9-]*"

_ENTITY_ID_RE = re.compile(
    rf"^(?P<prefix>[A-Z]{{2,6}})@(?P<epoch>\d+)\.(?P<random>[A-Za-z0-9-]+)(?:\.(?P<slug>{SLUG_PATTERN}))?$"
)


#: The slug as ``slugify`` actually emits it: hyphens separate alphanumeric runs and are
#: never doubled. Stricter than SLUG_PATTERN, which merely validates. The difference matters
#: when scanning free text rather than a whole-string match: a composite connection id joins
#: two artifact ids with ``---``, and a slug allowed to contain runs of hyphens swallows that
#: separator and the prefix of the endpoint after it.
_EMITTED_SLUG_PATTERN = r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*"


def full_ids_with_stem(stem: str) -> re.Pattern[str]:
    """Matches any full artifact id sharing the rename-stable *stem*, whatever its slug.

    The search key for "every reference to this entity, however it is currently spelled",
    used against file text that also contains composite connection ids. Anchored on the stem
    so ``GOL@1.Ab`` cannot match inside ``GOL@1.Abc.some-slug`` — the character after the
    stem must be the separating dot — and bounded so a match stops at a ``---`` join rather
    than consuming the endpoint on the far side of it.
    """
    return re.compile(rf"{re.escape(stem)}\.{_EMITTED_SLUG_PATTERN}")


class MalformedArtifactIdError(ValueError):
    pass


def stable_id(s: str) -> str:
    """Return the short (rename-stable) form of an artifact ID.

    A short ID (exactly one dot between epoch and random) is returned unchanged.
    A full ID (two dots — epoch, random, slug) has the trailing slug stripped.
    """
    if s.count(".") == 1:
        return s
    return s.rsplit(".", 1)[0]


def is_entity_id(s: str) -> bool:
    """True when *s* is a well-formed entity artifact ID (short or full form).

    The non-raising companion to ``parse_entity_id``, for callers that must treat
    a non-ID string as data rather than as an error — normalizing an arbitrary
    string with ``stable_id`` would silently truncate it at its last dot.
    """
    return _ENTITY_ID_RE.match(s) is not None


def canonical_entity_key(s: str) -> str:
    """The key an entity is matched under across stores: its stable form, or the string itself.

    Callers legitimately hold either form — the GUI navigates by the full
    ``PREFIX@epoch.random.slug`` id while scripts and MCP callers usually pass the short one — and
    a store that matches by exact string equality then treats the two as different elements. The
    symptom is never an error: the same element is listed twice, or a record filed under one form
    is invisible to a reader using the other.

    Anything that is not a well-formed entity id is returned unchanged, because ``stable_id``
    would truncate it at its last dot. Diagram-hosted node ids and synthetic test anchors both
    depend on that.
    """
    candidate = s.strip()
    return stable_id(candidate) if is_entity_id(candidate) else candidate


def slug_of(s: str) -> str | None:
    """Return the slug segment of an artifact ID, or None if absent."""
    if s.count(".") < 2:
        return None
    return s.rsplit(".", 1)[1]


def parse_entity_id(s: str) -> EntityId:
    """Parse and validate an entity artifact ID; raise MalformedArtifactIdError on failure."""
    m = _ENTITY_ID_RE.match(s)
    if m is None:
        raise MalformedArtifactIdError(f"Malformed artifact ID: {s!r}")
    return EntityId(
        prefix=m.group("prefix"),
        epoch=m.group("epoch"),
        random=m.group("random"),
        slug=m.group("slug"),
    )


@dataclass(frozen=True)
class EntityId:
    prefix: str
    epoch: str
    random: str
    slug: str | None

    @property
    def short(self) -> str:
        return f"{self.prefix}@{self.epoch}.{self.random}"

    def long(self, slug: str) -> str:
        return f"{self.prefix}@{self.epoch}.{self.random}.{slug}"


@dataclass(frozen=True)
class ConnectionKey:
    src_short: str
    type: str
    tgt_short: str

    def normalized(self, *, symmetric: bool) -> ConnectionKey:
        """Return a canonical form of this key.

        For symmetric relation types the endpoint order is sorted so that
        (A→B) and (B→A) produce the same key.  Directed relations keep
        their original order.
        """
        if symmetric and self.src_short > self.tgt_short:
            return ConnectionKey(
                src_short=self.tgt_short,
                type=self.type,
                tgt_short=self.src_short,
            )
        return self


def stable_conn_id(s: str) -> str:
    """Return the stable (slug-free) string form of a connection ID.

    Normalizes ``{src_long}---{tgt_long}@@{type}`` to
    ``{src_short}---{tgt_short}@@{type}``.  Returns *s* unchanged if malformed.
    """
    try:
        key = parse_connection_id(s)
        return f"{key.src_short}---{key.tgt_short}@@{key.type}"
    except MalformedArtifactIdError:
        return s


def parse_connection_id(s: str) -> ConnectionKey:
    """Parse a connection ID of the form '{src}---{tgt}@@{type}'.

    Both endpoints are canonicalized to their short (stable) form so that
    stale-slug and current-slug forms of the same connection compare equal.
    """
    at_at = s.find("@@")
    if at_at < 0:
        raise MalformedArtifactIdError(f"Malformed connection ID (missing @@): {s!r}")
    endpoints_part = s[:at_at]
    conn_type = s[at_at + 2 :]
    triple_dash = endpoints_part.find("---")
    if triple_dash < 0:
        raise MalformedArtifactIdError(f"Malformed connection ID (missing ---): {s!r}")
    src = endpoints_part[:triple_dash]
    tgt = endpoints_part[triple_dash + 3 :]
    if not src or not tgt or not conn_type:
        raise MalformedArtifactIdError(f"Malformed connection ID (empty segment): {s!r}")
    return ConnectionKey(
        src_short=stable_id(src),
        type=conn_type,
        tgt_short=stable_id(tgt),
    )

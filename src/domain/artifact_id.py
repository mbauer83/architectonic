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
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

#: The type prefix. Defined once for the same reason the slug and key patterns are: the endpoint
#: separator is told apart from a hyphen inside an id by "an id starts here", and a second copy of
#: what an id starts with is a second grammar to drift.
PREFIX_PATTERN = r"[A-Z]{2,6}"

#: The rename-volatile slug tail. Defined once: anything that needs to recognise a slug
#: must use this rather than restate the charset, or the two grammars drift apart and the
#: looser one silently matches text that is not part of an id.
SLUG_PATTERN = r"[A-Za-z0-9][A-Za-z0-9-]*"

#: The short random key, over the alphabet the generator actually draws from —
#: ``string.ascii_letters + string.digits + "-_"`` in ``application.modeling.artifact_write``.
#:
#: It said ``[A-Za-z0-9-]+`` until 2026-08-02, omitting the underscore, so this module rejected about
#: **9%** of the ids the product itself mints (six characters from a 64-symbol alphabet: 1 − (63/64)⁶).
#: Every other grammar in the codebase already allowed it — the verifier's ``ENTITY_ID_RE``, the
#: workspace identity rules, the datatype classifier pattern, and all three shipped frontmatter
#: JSON Schemas — so the canonical module was the one that had drifted.
#:
#: The damage was not a crash. ``is_entity_id`` returned False for such an id, so
#: ``canonical_entity_key`` handed back the *full* id instead of the stable short form, and its own
#: docstring already describes what that costs: "the same element is listed twice, or a record filed
#: under one form is invisible to a reader using the other". Thirty-odd call sites depend on that key,
#: most of them in the join between assurance nodes and architecture entities, and one entity in eleven
#: silently joined on the wrong form. Intermittency is why it survived: an id either has an underscore
#: or it does not, and nothing that mints one looks at it again.
RANDOM_KEY_PATTERN = r"[A-Za-z0-9_-]+"

_ENTITY_ID_RE = re.compile(
    rf"^(?P<prefix>{PREFIX_PATTERN})@(?P<epoch>\d+)\.(?P<random>{RANDOM_KEY_PATTERN})"
    rf"(?:\.(?P<slug>{SLUG_PATTERN}))?$"
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


def canonical_ids_by_stem(
    ids: Iterable[str], *, stem_of: Callable[[str], str] = stable_id
) -> dict[str, set[str]]:
    """Stem → every full id carrying it, for asking how an artifact is spelled *now*.

    A set rather than a single value: the engagement and enterprise tiers can both hold an artifact
    with the same stem, and picking one arbitrarily would report drift against a correct reference.
    ``stem_of`` selects the identity grammar — ``stable_id`` for entities, ``stable_conn_id`` for
    connections, whose stem joins two endpoint ids.
    """
    index: dict[str, set[str]] = {}
    for artifact_id in ids:
        index.setdefault(stem_of(artifact_id), set()).add(artifact_id)
    return index


def current_spelling_of(
    reference: str,
    canonical_ids: Mapping[str, set[str]],
    *,
    stem_of: Callable[[str], str] = stable_id,
) -> str | None:
    """The id *reference* would name if it were spelled currently — or None if there is nothing to say.

    Identity is the stem, so a reference holding a former slug still resolves everywhere: this is
    never a defect in resolution. It is worth reporting because the slug is the only part of an id a
    reader understands, and one naming a title the artifact no longer has misleads in review.

    None when the reference carries no slug at all: the stem alone is a legitimate spelling — it is
    the form the index itself keys artifacts under — and it names no title, so it misleads nobody.
    Only a slug that *was* a title and no longer is does that.

    Also None when the reference is already current, when the stem is unknown, and when the stem is
    ambiguous — with more than one candidate there is no single current spelling to name, and
    guessing would report drift against a correct reference. Ambiguity across tiers is diagnosed on
    its own by the resolver, not here.
    """
    if slug_of(reference) is None:
        return None
    candidates = canonical_ids.get(stem_of(reference), set())
    if len(candidates) != 1:
        return None
    canonical = next(iter(candidates))
    return None if canonical == reference else canonical


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


#: A well-formed id begins with its prefix and epoch, which is what tells the endpoint separator
#: apart from a hyphen belonging to the id before it.
_ID_START_RE = re.compile(rf"{PREFIX_PATTERN}@\d")


def _endpoint_split(endpoints_part: str) -> tuple[str, str] | None:
    """Split ``{src}---{tgt}`` at the separator, not at the first three hyphens in a row.

    The random key is drawn from ``letters + digits + "-_"``, so about one id in sixty-four ends in a
    hyphen — and for those, ``find("---")`` matched that hyphen plus the first two of the separator.
    The source came back a character short and the target with a leading ``-``, so the connection
    could not be found from either end: the write walk's `admin_delete_connection` answered
    "connection not found for source entity" for a connection that was right there, and did so on
    about one run in sixty-four, which is what made it look like flakiness rather than a defect.

    The separator is therefore the ``---`` an *id* follows, since no id may begin with a hyphen.
    """
    # Lookahead, so the candidates overlap: in ``----`` the separator is the *second* three, and a
    # non-overlapping scan consumes the first three and never offers it.
    for match in re.finditer("(?=---)", endpoints_part):
        start = match.start()
        if _ID_START_RE.match(endpoints_part, start + 3):
            return endpoints_part[:start], endpoints_part[start + 3 :]
    # Nothing that looks like an id follows any separator. Composite keys are also built over
    # placeholders that are not artifact ids at all — a derivation path step, a test's ``A---B`` —
    # and those have no hyphen-terminated-key ambiguity to resolve, so the plain split is right for
    # them. Preferring the id-aware answer and falling back keeps both readable.
    start = endpoints_part.find("---")
    if start < 0:
        return None
    return endpoints_part[:start], endpoints_part[start + 3 :]


def connection_id_as_written(s: str) -> tuple[str, str, str]:
    """A connection ID split into ``(source, target, type)`` with each endpoint left as spelled.

    The grammar lives here once. ``parse_connection_id`` collapses the endpoints to their stable
    form, which is right for identity and wrong for anything asking how the reference *reads* —
    and a second copy of the split is how the two answers drift apart.
    """
    at_at = s.find("@@")
    if at_at < 0:
        raise MalformedArtifactIdError(f"Malformed connection ID (missing @@): {s!r}")
    endpoints_part = s[:at_at]
    conn_type = s[at_at + 2 :]
    split = _endpoint_split(endpoints_part)
    if split is None:
        raise MalformedArtifactIdError(f"Malformed connection ID (missing ---): {s!r}")
    src, tgt = split
    if not src or not tgt or not conn_type:
        raise MalformedArtifactIdError(f"Malformed connection ID (empty segment): {s!r}")
    return src, tgt, conn_type


@dataclass(frozen=True)
class ConnectionReference:
    """One connection named in either of the two forms a caller may write it in.

    **Named fields rather than a tuple, and that is the point.** Three modules parsed these strings
    into a three-string tuple and two of them disagreed about the *order*: `(source, target, type)`
    in the bulk and sync readers, `(source, type, target)` in the promotion planner. Two functions
    returning the same shape with two of its fields transposed is a defect waiting for the first
    caller that is moved from one to the other, and no test would have caught it — both halves
    type-check and both look right at the call site.
    """

    source: str
    conn_type: str
    target: str


def parse_connection_reference(reference: str) -> ConnectionReference | None:
    """Either form a connection may be named in, or None when it is neither.

    * canonical — `{source}---{target}@@{type}`, delegated to `connection_id_as_written` so the
      hyphen-terminated-key ambiguity is resolved in the one place that knows about it;
    * as written by a caller — `{source} {type} → {target}`, which bulk operations, sync and
      promotion all accept.

    Three readings of this existed and disagreed on three things: `split` versus `rsplit` on the
    arrow, whether to strip each part, and the tuple order. Resolved as: the **first** arrow (an
    artifact id contains no spaces, so a well-formed reference has exactly one, and for a malformed
    one either answer is equally arbitrary — this one is stated rather than incidental), parts
    stripped, and a malformed canonical id is None rather than falling through to the arrow branch,
    since a string carrying `---` and `@@` was making the canonical claim.
    """
    if "---" in reference and "@@" in reference:
        try:
            source, target, conn_type = connection_id_as_written(reference)
        except MalformedArtifactIdError:
            return None
        return ConnectionReference(source=source.strip(), conn_type=conn_type.strip(), target=target.strip())
    if " → " not in reference:
        return None
    left, target = reference.split(" → ", 1)
    parts = left.split(" ", 1)
    if len(parts) < 2:
        return None
    return ConnectionReference(source=parts[0].strip(), conn_type=parts[1].strip(), target=target.strip())


def parse_connection_id(s: str) -> ConnectionKey:
    """Parse a connection ID of the form '{src}---{tgt}@@{type}'.

    Both endpoints are canonicalized to their short (stable) form so that
    stale-slug and current-slug forms of the same connection compare equal.
    """
    src, tgt, conn_type = connection_id_as_written(s)
    return ConnectionKey(
        src_short=stable_id(src),
        type=conn_type,
        tgt_short=stable_id(tgt),
    )


def current_connection_spelling(
    reference: str, canonical_entity_ids: Mapping[str, set[str]]
) -> str | None:
    """*reference* rewritten with each endpoint's current slug — or None if there is nothing to say.

    A connection is identified by its endpoints' stems and its type, which is the form the index
    keys it under: there is no stored slugged spelling of a connection to compare against. What can
    go stale is each endpoint's slug, and the entity index is what knows the current one. Reported
    per entry rather than per endpoint, because what a reader has to rewrite is the whole entry.
    """
    try:
        source, target, conn_type = connection_id_as_written(reference)
    except MalformedArtifactIdError:
        return None  # Malformed references are diagnosed where the reference is resolved.
    current_source = current_spelling_of(source, canonical_entity_ids) or source
    current_target = current_spelling_of(target, canonical_entity_ids) or target
    rewritten = f"{current_source}---{current_target}@@{conn_type}"
    return None if rewritten == reference else rewritten

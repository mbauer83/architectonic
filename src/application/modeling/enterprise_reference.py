"""What it means for an engagement artifact to name an enterprise one — declared once, read once.

Two artifact kinds point across the tier boundary: a `global-artifact-reference`, which proxies an
enterprise artifact, and a `proposed-change`, which proposes an edit to one (see
`proposed_change.py`). Both say which artifact they mean in frontmatter, and both are read by the
index, the verifier, the write path and the REST state layer.

**This module exists because that reading had five copies that disagreed.** `global-artifact-id` was
spelled at eight sites in eight modules under four constant names plus bare literals, and the
readings were not equivalent: the index buckets a GAR under its *stripped* target
(`_mem_store.py`, twice, in two independently written copies), while `find_existing_gar` compared the
raw value. So a GAR whose target carried a trailing space was indexed under one key and searched for
under another — the duplicate check could not see it, and a second GAR for the same enterprise
artifact would be created. The tolerant reading already existed; nothing consulted it.

`tests/architecture/test_each_syntax_has_one_reader.py` is the register that names this rule. The
same class of defect has now been fixed four times.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.application.modeling.edit_field_catalogue import PROPOSABLE, ArtifactKind

#: The internal artifact type that proxies an enterprise artifact.
GLOBAL_ARTIFACT_REFERENCE_TYPE = "global-artifact-reference"

#: The frontmatter field naming the enterprise artifact a reference proxies.
GLOBAL_ARTIFACT_ID = "global-artifact-id"

#: Which kind of artifact is proxied — an entity, a document or a diagram. A reference's connection
#: surface exists only for the entity kind, which is why three call sites compared this field against
#: `"entity"`; `proxies_an_entity` is that question with a name.
GLOBAL_ARTIFACT_KIND = "global-artifact-type"

#: The proxied artifact's own type, cached on the reference so endpoint legality can be judged
#: without the enterprise repository being loaded.
GLOBAL_ARTIFACT_ENTITY_TYPE = "global-artifact-entity-type"

#: The kind value that carries a connection surface.
ENTITY_KIND = "entity"


def enterprise_target(fields: Mapping[str, object]) -> str | None:
    """The enterprise artifact this frontmatter names, or None where it names none.

    Tolerant of surrounding whitespace, because the index has always been and the disagreement went
    one way only: a value the index accepted and a matcher rejected produced a duplicate, never a
    missed one. Empty after stripping is *no target* rather than the empty-string target, so a field
    left blank by an editor cannot bucket every such artifact together under `""`.
    """
    target = fields.get(GLOBAL_ARTIFACT_ID)
    return stripped if isinstance(target, str) and (stripped := target.strip()) else None


def proxied_kind(fields: Mapping[str, object]) -> ArtifactKind | None:
    """Which kind of artifact this reference stands for, or None where it names none this can hold.

    A reference proxies an entity, a document or a diagram, and *which* decides the vocabulary an
    edit of it may use: a change to the promoted document `General coding guidelines` says `title`
    and `body`, and a change to a promoted requirement says `summary` and `properties`. Reading the
    field is one question with one answer, so it is asked here rather than by whoever needs the
    vocabulary — a caller that assumed the entity kind recorded document edits under the entity
    catalogue, which is the defect this replaces.

    None for anything outside `PROPOSABLE`, including a missing or misspelled value: a reference
    whose kind cannot be read is one nothing should guess about.
    """
    declared = fields.get(GLOBAL_ARTIFACT_KIND)
    return next((kind for kind in PROPOSABLE if kind == declared), None)


def proxies_an_entity(fields: Mapping[str, object]) -> bool:
    """Whether this reference stands for an *entity*, and so has a connection surface at all.

    A reference to a document or a diagram proxies something nothing can connect to, which is why
    the connection routes ask this before offering endpoints.
    """
    return proxied_kind(fields) == ENTITY_KIND

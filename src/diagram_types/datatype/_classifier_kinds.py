"""What kind of classifier a declaration says it is, read in one place.

`classifier_kind` is declared on `classifier` entities in `ontology.yaml` and reaches a reader from
two sources that look nothing alike — an `EntityRecord.extra` for a committed classifier, and the
raw `diagram-entities` mapping for one declared inline in the diagram under verification. Both are
mappings by the time anyone reads the field, so both go through here.

The field is what tells a *primitive* apart from a class, a datatype or an enumeration, and that
distinction had no reader outside the renderer and the verification projection: the type catalog
answered `kind="classifier"` for every row, so a custom primitive was indistinguishable from a
structured type in the one answer built for choosing a type.
"""

from __future__ import annotations

from collections.abc import Mapping

#: A leaf type with no internal structure — `Integer`, `String`, or one a repository declares for
#: itself. The kind the catalog has to be able to name, because a primitive is offered beside the
#: built-in scalars rather than among the structured types.
PRIMITIVE_KIND = "primitive"

#: What a classifier is when its declaration says nothing. `ontology.yaml` marks `classifier_kind`
#: required, so this is the reading's floor rather than a documented default.
DEFAULT_KIND = "class"


def classifier_kind_of(source: Mapping[str, object]) -> str:
    """The kind *source* declares, or `DEFAULT_KIND` where it declares none."""
    return str(source.get("classifier_kind") or "") or DEFAULT_KIND


def is_primitive(source: Mapping[str, object]) -> bool:
    """Whether *source* declares a leaf scalar type rather than a structured one."""
    return classifier_kind_of(source) == PRIMITIVE_KIND

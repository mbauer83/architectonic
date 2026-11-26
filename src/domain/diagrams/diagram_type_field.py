"""Which diagram type a diagram's frontmatter states, and what a diagram that states none is read as.

The one reading of the `diagram-type` field. Two answers are asked of it, and both live here so they
cannot come to disagree about what "stated" means:

* `stated_diagram_type` — the type as written, or `""` when the field is absent or empty. For the
  checks that must tell a missing type from a present one (the verifier, which reports it).
* `diagram_type_of` — the type a diagram is drawn and edited as. A diagram written before the field
  was required states none, and is an ArchiMate diagram: `UNSTATED_DIAGRAM_TYPE`.

The field is required by the diagram schema, so the default serves only such older files; a write
path that reads it does not then have to decide for itself what a missing value means.
"""

from __future__ import annotations

from collections.abc import Mapping

#: The frontmatter key a diagram states its type under.
DIAGRAM_TYPE_KEY = "diagram-type"

#: What a diagram that states no type is drawn and edited as.
UNSTATED_DIAGRAM_TYPE = "archimate"


def stated_diagram_type(frontmatter: Mapping[str, object]) -> str:
    """The diagram type *frontmatter* states, stripped; `""` when it states none."""
    value = frontmatter.get(DIAGRAM_TYPE_KEY)
    return "" if value is None else str(value).strip()


def diagram_type_of(frontmatter: Mapping[str, object]) -> str:
    """The diagram type a diagram is drawn as: the one it states, else `UNSTATED_DIAGRAM_TYPE`."""
    return stated_diagram_type(frontmatter) or UNSTATED_DIAGRAM_TYPE

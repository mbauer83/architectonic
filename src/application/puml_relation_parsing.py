"""The relations a PlantUML body declares — one reader, for every caller that needs them.

Three copies of this parsing existed (diagram reconcile, diagram-reference rewriting, and the
verifier rule for PUML relations), all recognising exactly two forms: a ``Rel_Xxx(src, tgt)`` macro
call and an arrow carrying a ``: <<Stereotype>>`` label. The generated bodies in this repository use
**neither** — the renderer emits bare arrows (``FNC_a --> FNC_b``, ``ASS_x ..> GOL_y``) and leaves
the ``!define Rel_*`` lines in the header uncalled.

So every reader saw a generated diagram as declaring no relations at all. For the reconcile path
that meant the binding set could never be recovered from the body, and any relation drawn but not
bound was deleted on the next refresh — six real ``archimate-influence`` relations were lost from
one view that way. For the verifier it meant the rule that should have caught the divergence was
blind to the same thing. Copies of a rule drift, and these had drifted into failing open.

A bare arrow names its endpoints but not its type: ``..>`` is the declared ``puml_arrow`` of both
``archimate-access`` and ``archimate-influence``, so the glyph cannot identify the relation.
``connection_type`` is therefore None for that form, and the caller resolves it against the model
(where the pair usually has exactly one connection). The drawn glyph is carried along so a caller
with more than one candidate can still choose.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from src.application.puml_alias_declarations import alias_declared_on

#: `Rel_Triggering(A, B, …)` — the macro form.
_REL_MACRO_RE = re.compile(
    r"^\s*Rel_(?P<rel>[A-Za-z0-9]+)(?:_(?:Up|Down|Left|Right))?"
    r"\(\s*(?P<src>[A-Za-z0-9_-]+)\s*,\s*(?P<tgt>[A-Za-z0-9_-]+)",
    re.MULTILINE,
)
#: `A --> B : <<archimate-serving>>` — an arrow whose label states the type.
_REL_LINE_RE = re.compile(
    r"^\s*(?P<src>[A-Za-z0-9_-]+)\s+(?P<arrow>[-.*|o<>][^\n:]*?)\s+(?P<tgt>[A-Za-z0-9_-]+)"
    r"\s*:\s*<<(?P<rel>[A-Za-z]+)>>",
    re.MULTILINE,
)
#: `A --> B`, optionally with a plain label — the form the renderer actually emits.
_BARE_ARROW_RE = re.compile(
    r"^\s*(?P<src>[A-Za-z0-9_-]+)\s+(?P<arrow>[-.*|o<>][^\s]*[-.*|o<>])\s+(?P<tgt>[A-Za-z0-9_-]+)"
    r"\s*(?::\s*(?P<label>[^\n]*))?$",
    re.MULTILINE,
)
#: A stereotype label is the typed form above, not a plain one.
_STEREOTYPE_LABEL_RE = re.compile(r"^\s*<<[A-Za-z]+>>\s*$")


@dataclass(frozen=True)
class DeclaredRelation:
    """One relation a body draws between two aliases."""

    source_alias: str
    target_alias: str
    #: The connection type the body states, or None when it states only an arrow.
    connection_type: str | None
    #: The drawn glyph (`-->`, `..>`, `.up.|>`), for choosing among candidate types.
    arrow: str


#: Container versus leaf is `opens_block` on the one declaration reading — see
#: `puml_alias_declarations`. It used to be two regexes here, each anchoring the alias to the end of
#: the line, which made "leaf" mean "nothing follows the alias": a trailing `#colour` then left an
#: element neither container nor leaf, so its containment was never read and its nesting was lost.


def _is_layout_only(arrow: str) -> bool:
    """A hidden link positions elements and asserts no relation."""
    return "[hidden]" in arrow


def _containment_relations(content: str) -> list[DeclaredRelation]:
    """Relations the body states by nesting one element inside another.

    PlantUML draws composition and aggregation as containment, so a body can assert a relation
    without drawing any arrow for it — and reading arrows alone made those invisible. That cost a
    view its structure: `reverse-architecture-architecture-conformance-review` nests its functions
    inside the processes that orchestrate them, the containment was never read back into the binding
    set, and the refreshed diagram had no structural edges left to nest by, so it collapsed into
    boxes grouped by element type.

    A grouping rectangle carries no alias (`rectangle "Processes" <<CommonGrouping>> {`), so it
    contributes no parent and its members are not mistaken for its children. Where an authored body
    does alias a grouping, the alias resolves to no entity and the caller drops it.
    """
    found: list[DeclaredRelation] = []
    stack: list[str] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith(("'", "!", "@", "title", "sprite")):
            continue
        if line == "}":
            if stack:
                stack.pop()
            continue
        declaration = alias_declared_on(line)
        if declaration is not None and declaration.opens_block:
            if stack and stack[-1]:
                found.append(DeclaredRelation(stack[-1], declaration.alias, None, ""))
            stack.append(declaration.alias)
            continue
        if declaration is None and line.endswith("{"):
            # A grouping rectangle or a `skinparam …{` block: opens a scope, names no parent.
            stack.append("")
            continue
        if declaration is not None and stack and stack[-1]:
            found.append(DeclaredRelation(stack[-1], declaration.alias, None, ""))
    return found


def declared_relations(
    content: str,
    stereotype_map: Mapping[str, str],
) -> list[DeclaredRelation]:
    """Every relation *content* draws, in the order drawn, across all three forms.

    Anchored per line, which is what keeps the ``!define Rel_Triggering(from, to, label) from --> to``
    header lines out: they begin with ``!define``, so neither the macro form (which expects the call
    at line start) nor the bare-arrow form matches them. A hidden layout link is never a relation.
    """
    found: list[DeclaredRelation] = []
    typed_positions: set[tuple[str, str]] = set()

    for match in _REL_MACRO_RE.finditer(content):
        conn_type = stereotype_map.get(match.group("rel").lower())
        if conn_type is not None:
            found.append(DeclaredRelation(match.group("src"), match.group("tgt"), conn_type, ""))

    for match in _REL_LINE_RE.finditer(content):
        if _is_layout_only(match.group("arrow")):
            continue
        conn_type = stereotype_map.get(match.group("rel").lower())
        typed_positions.add((match.group("src"), match.group("tgt")))
        if conn_type is not None:
            found.append(
                DeclaredRelation(match.group("src"), match.group("tgt"), conn_type, match.group("arrow"))
            )

    for match in _BARE_ARROW_RE.finditer(content):
        arrow = match.group("arrow")
        if _is_layout_only(arrow):
            continue
        label = match.group("label")
        # The stereotyped form is already handled above; re-reading it here would double-count it
        # as an untyped relation and discard the type the body stated.
        if label is not None and _STEREOTYPE_LABEL_RE.match(label):
            continue
        if (match.group("src"), match.group("tgt")) in typed_positions:
            continue
        found.append(DeclaredRelation(match.group("src"), match.group("tgt"), None, arrow))

    found.extend(_containment_relations(content))
    return found

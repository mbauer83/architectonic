"""Auto-layout engine for PlantUML diagrams.

Analyzes diagram structure (groupings, elements, connections) and inserts
layout optimizations for ortho routing:

- Hidden links spread elements within groupings (orthogonal to main flow)
- Arrow direction hints guide inter-layer connection routing
- Direction selection uses heuristics based on group/element counts
"""

import re
from dataclasses import dataclass, field

from src.application.modeling.flow_ordering import order_aliases_along_flow


@dataclass
class _GroupInfo:
    """A top-level rectangle grouping and its contained element aliases."""

    label: str
    aliases: list[str] = field(default_factory=list)
    index: int = 0


def _parse_groupings(puml: str) -> list[_GroupInfo]:
    """Extract top-level rectangle groupings and their nested element aliases.

    Handles arbitrary nesting depth — all element aliases within a top-level
    grouping are collected regardless of sub-grouping structure.
    """
    lines = puml.split("\n")
    result: list[_GroupInfo] = []
    current: _GroupInfo | None = None
    depth = 0
    group_idx = 0

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("'") or not stripped:
            continue

        # Top-level grouping: rectangle "..." <<...>> ... {
        if depth == 0 and "rectangle" in stripped and "{" in stripped:
            m = re.match(r'rectangle\s+"([^"]+)"', stripped)
            if m:
                current = _GroupInfo(label=m.group(1), index=group_idx)
                group_idx += 1
                result.append(current)

        # Element with alias inside a grouping (has `as ALIAS`, no trailing `{`)
        # Note: sprite labels like <$name{scale=0.9}> contain `{` mid-line, so we
        # only exclude lines where `{` appears at the end (container openings).
        # Strip quoted strings before searching to avoid matching "as" inside label text
        # (e.g. "AI-Assisted Development as Dominant Production Mode").
        elif current is not None and depth > 0:
            without_quotes = re.sub(r'"[^"]*"', '""', stripped)
            m = re.search(r"\bas\s+(\w+)", without_quotes)
            if m and not re.search(r"\{\s*$", stripped):
                current.aliases.append(m.group(1))

        depth += stripped.count("{") - stripped.count("}")

        if current is not None and depth == 0:
            current = None

    return result


def _detect_direction(puml: str) -> str | None:
    """Detect an existing direction directive in the PUML body."""
    m = re.search(r"(top to bottom|left to right)\s+direction", puml)
    return m.group(1) if m else None


def _select_direction(groups: list[_GroupInfo]) -> str:
    """Select optimal direction based on diagram structure metrics.

    Heuristics:
    - >= 2 top-level groupings or max elements per group <= 5: top to bottom
      (standard ArchiMate layered layout, elements spread horizontally)
    - <= 1 grouping with many (>= 6) elements: left to right
    """
    n_groups = len(groups)
    max_elems = max((len(g.aliases) for g in groups), default=0)

    if n_groups <= 1 and max_elems >= 6:
        return "left to right"
    return "top to bottom"


# Regex matching a connection line:  ALIAS <arrow> ALIAS [: label]
# Arrow must start and end with a connector character.
_CONN_LINE_RE = re.compile(
    r"^(\s*)"  # (1) leading whitespace
    r"(\w+)"  # (2) source alias
    r"(\s+)"  # (3) space
    r"([-.*|o<>][^\s]*?[-.*|o<>])"  # (4) arrow (bracket/direction/color inside)
    r"(\s+)"  # (5) space
    r"(\w+)"  # (6) target alias
    r"(\s*(?::\s*.*)?)$"  # (7) optional : label
)

_MACRO_CONN_RE = re.compile(
    r"^(\s*)"
    r"(Rel_[A-Za-z0-9]+)"
    r"(?:_(Up|Down|Left|Right))?"
    r"\(\s*(\w+)\s*,\s*(\w+)(.*)\)\s*$"
)


#: Relation kinds that express a sequence. Only these order a grouping's members: an
#: association or access says two elements are related, not that one comes after the other,
#: and ordering by them would be a claim the model does not make.
_SEQUENCING_MACROS = frozenset({"Rel_Triggering", "Rel_Flow", "Rel_Serving", "Rel_Realization"})


def _directed_pairs(puml: str) -> list[tuple[str, str]]:
    """Every (source, target) the body states with a sequencing relation."""
    pairs: list[tuple[str, str]] = []
    for line in puml.split("\n"):
        if "[hidden]" in line:
            continue
        macro = _MACRO_CONN_RE.match(line)
        if macro is not None:
            if macro.group(2) in _SEQUENCING_MACROS:
                pairs.append((macro.group(4), macro.group(5)))
            continue
        plain = _CONN_LINE_RE.match(line)
        # A bare arrow only counts when it actually points: `A --> B` sequences, `A -- B`
        # is an association drawn as a line and says nothing about order.
        if plain is not None and ">" in plain.group(4):
            pairs.append((plain.group(2), plain.group(6)))
    return pairs


def _flow_ordered(aliases: list[str], pairs: list[tuple[str, str]]) -> list[str]:
    """Order *aliases* by the flow they express, but only when that flow is unambiguous.

    The hidden spread chain is itself the rank constraint — ``A -[hidden]right- B`` already
    tells Graphviz that A precedes B on the spread axis. What was wrong was the sequence it
    encoded: aliases arrive in declaration order (by artifact type, then label), so a pipeline
    ``A → B → C`` could be pinned out as ``C, A, B`` and its arrows had to double back across
    the whole grouping. Re-sequencing the same links fixes the picture without adding a single
    constraint, hint, or arrow.

    Declaration order is by artifact type, then label — which is uncorrelated with flow and
    frequently its exact opposite, because a role performs a process that realizes a service
    while ``PRC`` < ``ROL`` < ``SRV``. Across this repository 21 of 38 intra-grouping
    sequencing edges pointed backwards along the spread axis, and one grouping had all eight
    of its edges reversed. Preserving the type grouping is what produced that, so it is not
    worth preserving here.

    The ordering itself is `flow_ordering` beside this module, shared with the renderer that
    generates a body from model records rather than rewriting an authored one. Only the way the
    directed pairs are obtained differs between the two — parsed arrows here, connection records
    there — and a second copy of the rule is what let the generated path keep chaining members in
    id order long after this path was corrected.
    """
    return order_aliases_along_flow(aliases=aliases, flow_edges=pairs)


#: Header comment marking the block this module emits, so it can recognise its own output.
AUTO_BLOCK_COMMENT = "' --- Auto-layout: spread elements within groupings ---"

_HIDDEN_LINK_RE = re.compile(r"^\s*\w+ -\[hidden\]\w+- \w+\s*$")


def _strip_auto_block(puml: str) -> str:
    """Remove a block this module previously emitted, leaving every other line untouched.

    The exact inverse of what phase 3 inserts — one blank line, the comment, the links, one
    blank line — so that stripping and re-emitting round-trips. Consuming blank lines greedily
    instead would eat a separator the author wrote, and optimizing an already-optimized body
    would then differ from optimizing it once.
    """
    if AUTO_BLOCK_COMMENT not in puml:
        return puml
    kept: list[str] = []
    lines = puml.split("\n")
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.strip() != AUTO_BLOCK_COMMENT.strip():
            kept.append(line)
            index += 1
            continue
        if kept and kept[-1].strip() == "":
            kept.pop()  # the single blank the emitter puts before the comment
        index += 1
        while index < len(lines) and _HIDDEN_LINK_RE.match(lines[index]):
            index += 1
        if index < len(lines) and not lines[index].strip():
            index += 1  # ...and the single blank it puts after the links
    return "\n".join(kept)


def _insert_arrow_direction(arrow: str, direction: str) -> str:
    """Insert a direction hint into PlantUML arrow syntax.

    Returns the arrow unchanged if it already contains a direction keyword
    or is a hidden link.
    """
    if "[hidden]" in arrow:
        return arrow
    if re.search(r"(up|down|left|right)", arrow):
        return arrow

    # Bracket syntax: -[#color]-> → -[#color]down->
    m = re.match(r"(.*\])(.+)", arrow)
    if m:
        return m.group(1) + direction + m.group(2)

    # Dot arrow: ..> → .down.>
    if arrow.startswith("."):
        return "." + direction + arrow[1:]

    # Dash arrow: --> → -down->, -|> → -down-|>, -- → -down-
    if arrow.startswith("-"):
        rest = arrow[1:]
        sep = "" if rest.startswith("-") else "-"
        return "-" + direction + sep + rest

    return arrow


def ensure_puml_layout(puml_body: str) -> str:
    """Lay out a diagram that has no arrangement yet; leave one that has.

    A hand-tuned diagram stays hand-tuned, so editing a diagram's name, bindings or metadata
    cannot silently re-rank a body somebody arranged deliberately. Use this wherever laying
    out is incidental to the caller's real purpose.

    Args:
        puml_body: PUML content including @startuml/@enduml markers.

    Returns:
        The arranged body, or the original unchanged if it already carries an arrangement.
    """
    return _arrange(puml_body, original=puml_body)


def rebuild_puml_layout(puml_body: str) -> str:
    """Recompute the arrangement, discarding the block this module previously emitted.

    The opposite bargain from `ensure_puml_layout`, and it belongs only to actions whose
    stated purpose is to rebuild the picture — syncing a diagram against the model. Even
    then only this module's own block is replaced; hidden links it did not write are left
    alone, so a manual arrangement survives a sync too.

    Args:
        puml_body: PUML content including @startuml/@enduml markers.

    Returns:
        The re-arranged body.
    """
    return _arrange(_strip_auto_block(puml_body), original=puml_body)


def _arrange(puml_body: str, *, original: str) -> str:
    """Insert ortho-routing layout into `puml_body`, or hand back `original` untouched.

    Analyzes the grouping/element/connection structure and inserts:
    1. A direction directive (if not already present)
    2. Hidden links to spread elements within each grouping
    3. Arrow direction hints on inter-grouping connections

    Idempotent: yields the body unchanged if hidden links already exist or if the diagram has
    no groupings to arrange. `original` is what a caller gets back in that case, which is how
    `rebuild_puml_layout` restores the block it speculatively stripped when it turns out there
    was nothing to replace it with.
    """
    groups = _parse_groupings(puml_body)

    # Existing hidden links mean somebody has already decided how this diagram is ranked —
    # either a previous run of this module, or an author by hand. Neither is second-guessed;
    # on the rebuild path this module's own block is already gone by now, so anything still
    # here is hand-written and still off limits.
    if not groups or "[hidden]" in puml_body:
        return original

    # Only optimize groups that have 2+ elements to spread
    spreadable = [g for g in groups if len(g.aliases) >= 2]
    if not spreadable:
        return puml_body

    # --- Direction ---
    existing_dir = _detect_direction(puml_body)
    direction = existing_dir or _select_direction(groups)
    spread_dir = "right" if direction == "top to bottom" else "down"
    flow_dir = "down" if direction == "top to bottom" else "right"
    reverse_dir = "up" if direction == "top to bottom" else "left"

    # Alias → grouping index for arrow direction hints
    alias_to_group: dict[str, int] = {}
    for g in groups:
        for alias in g.aliases:
            alias_to_group[alias] = g.index

    lines = puml_body.split("\n")

    # --- Phase 1: Insert direction directive if missing ---
    if existing_dir is None:
        insert_idx = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if "@startuml" in stripped or stripped.startswith("!include"):
                insert_idx = i + 1
        lines.insert(insert_idx, "")
        lines.insert(insert_idx + 1, f"{direction} direction")

    # --- Phase 2: Add arrow direction hints to inter-grouping connections ---
    for i, line in enumerate(lines):
        m = _CONN_LINE_RE.match(line)
        if m:
            src_alias = m.group(2)
            arrow = m.group(4)
            tgt_alias = m.group(6)

            src_group = alias_to_group.get(src_alias)
            tgt_group = alias_to_group.get(tgt_alias)

            if src_group is None or tgt_group is None:
                continue
            if src_group == tgt_group:
                continue  # Intra-grouping — don't add layer hints

            hint = flow_dir if src_group < tgt_group else reverse_dir
            new_arrow = _insert_arrow_direction(arrow, hint)
            if new_arrow != arrow:
                lines[i] = m.group(1) + m.group(2) + m.group(3) + new_arrow + m.group(5) + m.group(6) + m.group(7)
            continue

        macro = _MACRO_CONN_RE.match(line)
        if not macro:
            continue

        src_alias = macro.group(4)
        tgt_alias = macro.group(5)
        src_group = alias_to_group.get(src_alias)
        tgt_group = alias_to_group.get(tgt_alias)
        if src_group is None or tgt_group is None or src_group == tgt_group:
            continue
        if macro.group(3):
            continue
        hint = flow_dir if src_group < tgt_group else reverse_dir
        lines[i] = (
            macro.group(1)
            + macro.group(2)
            + "_"
            + hint.title()
            + "("
            + src_alias
            + ", "
            + tgt_alias
            + macro.group(6)
            + ")"
        )

    # --- Phase 3: Generate hidden links block ---
    # In TB mode, elements within groupings need horizontal spread (hidden right links).
    # In LR mode, elements already stack vertically by default — adding hidden down
    # links is redundant and can over-constrain Graphviz, causing layout failures.
    if direction == "top to bottom" and spreadable:
        hidden_block: list[str] = [
            "",
            AUTO_BLOCK_COMMENT,
        ]
        pairs = _directed_pairs(puml_body)
        for g in spreadable:
            ordered = _flow_ordered(g.aliases, pairs)
            for j in range(len(ordered) - 1):
                hidden_block.append(f"{ordered[j]} -[hidden]{spread_dir}- {ordered[j + 1]}")
        hidden_block.append("")

        # Insert after the last top-level closing brace (between declarations and connections)
        insert_at = len(lines) - 1  # fallback: before @enduml
        depth = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            depth += stripped.count("{") - stripped.count("}")
            if depth == 0 and "}" in stripped:
                insert_at = i + 1

        for j, hline in enumerate(hidden_block):
            lines.insert(insert_at + j, hline)

    return "\n".join(lines)

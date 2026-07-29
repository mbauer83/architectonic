"""Emit authored groupings — user-declared boxes the model does not hold.

Authored groupings are CONTENT, not layout: their labels carry information
(a "Write Requests" box says something no element type does), so they render
exactly as declared — before any computed grouping, members in declared order.
Modelled containment wins for a member that is already visually nested.
"""

from __future__ import annotations

from collections.abc import Callable

from src.application.artifact_parsing import normalize_puml_alias
from src.domain.artifact_id import stable_id
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.infrastructure.rendering._diagram_layout import wrapped_grid_lines


def render_authored_groupings(
    authored_groupings: list[dict[str, object]],
    *,
    render_entities: list[EntityRecord],
    nested_aliases: set[str],
    domain_entities: dict[str, list[EntityRecord]],
    render_entity: Callable[..., list[str]],
    direction_hints: dict[tuple[str, str], str] | None = None,
    connected_pairs: frozenset[frozenset[str]] = frozenset(),
) -> list[str]:
    """Lines for every authored grouping; claimed members leave the domain pools.

    ``direction_hints`` (when given) receives left/right hints for connections whose
    BOTH endpoints sit in the same group, following the declared member order — so
    intra-group arrows run along the group instead of stacking members vertically.
    Groups chain via their own aliases: a hidden edge from a member of one box to a
    member of another crashes GraphViz."""
    resolved_groups = resolve_authored_members(authored_groupings, render_entities)
    taken_aliases: set[str] = set()
    previous_alias: str | None = None
    previous_members: list[str] = []
    group_counter = 0
    group_rank_by_alias: dict[str, int] = {}
    lines: list[str] = []
    for group, member_records in resolved_groups:
        if not member_records:
            continue
        stereotype = str(group.get("stereotype") or "CommonGrouping")
        group_counter += 1
        group_alias = f"GRPA_{group_counter}"
        lines.append(f'rectangle "{str(group.get("label", ""))}" <<{stereotype}>> as {group_alias} {{')
        for record, _alias in member_records:
            lines.extend(render_entity(record, "  ", "right"))
        lines.append("}")
        member_aliases = [alias for _record, alias in member_records]
        if len(member_aliases) > 4:
            lines.extend(wrapped_grid_lines(member_aliases, main_axis="right", cross_axis="down", indent=""))
        else:
            for idx in range(len(member_aliases) - 1):
                lines.append(f"{member_aliases[idx]} -[hidden]right- {member_aliases[idx + 1]}")
        taken_aliases.update(member_aliases)
        for alias in member_aliases:
            group_rank_by_alias[alias] = group_counter
        if direction_hints is not None:
            order = {alias: idx for idx, alias in enumerate(member_aliases)}
            for src in member_aliases:
                for tgt in member_aliases:
                    if src != tgt:
                        direction_hints.setdefault((src, tgt), "right" if order[tgt] > order[src] else "left")
        connected = any(
            frozenset((prev, curr)) in connected_pairs
            for prev in previous_members
            for curr in member_aliases
        )
        # A hidden edge between two boxes crashes GraphViz shape-dependently; when
        # arrows already join the groups, their direction hints do the ranking.
        if previous_alias and not connected:
            lines.append(f"{previous_alias} -[hidden]down- {group_alias}")
        previous_alias = group_alias
        previous_members = member_aliases
        lines.append("")

    # An arrow between two different authored groups follows the DECLARED group
    # order — the authored top-down organization is intentional and outranks the
    # arrow's natural rank direction.
    if direction_hints is not None:
        for src, src_rank in group_rank_by_alias.items():
            for tgt, tgt_rank in group_rank_by_alias.items():
                if src_rank != tgt_rank:
                    direction_hints.setdefault((src, tgt), "down" if tgt_rank > src_rank else "up")
    for domain in list(domain_entities):
        domain_entities[domain] = [
            entity
            for entity in domain_entities[domain]
            if normalize_puml_alias(entity.display_alias) not in taken_aliases
        ]
    return lines


def resolve_authored_members(
    authored_groupings: list[dict[str, object]],
    render_entities: list[EntityRecord],
) -> list[tuple[dict[str, object], list[tuple[EntityRecord, str]]]]:
    """Resolve each authored group's member ids to (record, alias), in declared order.

    A member may appear in one group only (first declaration wins). Membership in an
    authored group WINS over modelled containment nesting: the caller uses these
    aliases to release members from the visual-nesting tree before rendering.
    """
    record_by_short = {stable_id(entity.artifact_id): entity for entity in render_entities}
    claimed: set[str] = set()
    resolved: list[tuple[dict[str, object], list[tuple[EntityRecord, str]]]] = []
    for group in authored_groupings:
        if not isinstance(group, dict):
            continue
        member_records: list[tuple[EntityRecord, str]] = []
        raw_members = group.get("entity-ids")
        for raw_id in raw_members if isinstance(raw_members, list) else []:
            record = record_by_short.get(stable_id(str(raw_id)))
            alias = normalize_puml_alias(record.display_alias) if record is not None else ""
            if record is None or not alias or alias in claimed:
                continue
            member_records.append((record, alias))
            claimed.add(alias)
        resolved.append((group, member_records))
    return resolved

"""The boxes a body computes when its diagram states none: one per domain, stacked in layer order.

Moved out of the renderer as it stood. Domain boxes stack in the ontology's declared layer order
(motivation above strategy above business, common, application, technology); the alias lets a hidden
chain enforce that rank on the canvas.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence

from src.application.artifacts.parsing import normalize_puml_alias
from src.domain.diagrams.layout.box_aliases import domain_box_alias
from src.domain.ontology_representation.artifact_types import EntityRecord


def render_domain_boxes(
    ordered_domain_keys: Sequence[str],
    domain_entities: Mapping[str, list[EntityRecord]],
    *,
    canvas: Callable[..., list[str]],
    stereotype_of: Callable[[str], str],
    connection_alias_pairs: frozenset[frozenset[str]],
    domain_rank_by_alias: dict[str, int],
) -> list[str]:
    """One box per domain that still has something to show; fills *domain_rank_by_alias* for the arrows."""
    lines: list[str] = []
    previous_domain_alias: str | None = None
    previous_domain_members: set[str] = set()
    for domain_rank, domain in enumerate(ordered_domain_keys):
        for entity in domain_entities[domain]:
            alias = normalize_puml_alias(entity.display_alias)
            if alias:
                domain_rank_by_alias[alias] = domain_rank
    # Only the domains with something left to show. Claiming empties a domain's list
    # rather than removing the domain, so one an authored grouping emptied still has a key
    # here — and drew an empty labelled box, which a cross-domain grouping makes routine.
    for domain in (key for key in ordered_domain_keys if domain_entities[key]):
        domain_alias = domain_box_alias(domain)
        lines.append(f'rectangle "{domain.title()}" <<{stereotype_of(domain)}>> as {domain_alias} {{')
        # The same component canvas runs INSIDE each domain box — a domain used
        # to emit its members unordered, which erased the flow entirely.
        lines.extend(
            canvas(
                top_entities=domain_entities[domain],
                grouping=stereotype_of(domain),
                indent="  ",
                alias_namespace=f"{re.sub(r'[^A-Za-z0-9_]', '_', domain)}_",
            )
        )
        lines.append("}")
        domain_aliases = {
            alias for entity in domain_entities[domain] if (alias := normalize_puml_alias(entity.display_alias))
        }
        domains_connected = any(
            frozenset((prev, curr)) in connection_alias_pairs
            for prev in previous_domain_members
            for curr in domain_aliases
        )
        if previous_domain_alias and not domains_connected:
            lines.append(f"{previous_domain_alias} -[hidden]down- {domain_alias}")
        previous_domain_alias = domain_alias
        previous_domain_members = domain_aliases
        lines.append("")
    return lines

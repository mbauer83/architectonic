"""Data-driven admissibility checks for derived relationships."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, EntityTypeInfo
from src.domain.relationships.derivation_domains import DerivationDomain, derivation_domain


@dataclass(frozen=True)
class DerivationRestriction:
    """One declarative restriction on a relationship-composition result."""

    spec_ref: str
    source_domains: frozenset[DerivationDomain] = frozenset()
    target_domains: frozenset[DerivationDomain] = frozenset()
    target_domains_excluded: frozenset[DerivationDomain] = frozenset()
    source_artifact_types: frozenset[str] = frozenset()
    source_artifact_types_excluded: frozenset[str] = frozenset()
    intermediate_artifact_types: frozenset[str] = frozenset()
    source_passive: bool | None = None
    target_passive: bool | None = None
    connection_artifact_types: frozenset[str] = frozenset()
    allowed_connection_artifact_types: frozenset[str] = frozenset()
    intermediate_domain_must_match_endpoint: bool = False
    intermediate_domain_exception: bool = False
    always_disallow: bool = False


def restriction_rules_from_mapping(raw: object) -> tuple[DerivationRestriction, ...]:
    """Validate ontology-supplied relationship-derivation restriction data."""
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ValueError("relationship derivation restrictions must be a sequence")
    rules: list[DerivationRestriction] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("relationship derivation restriction must be a mapping")
        try:
            rules.append(
                DerivationRestriction(
                    spec_ref=_required_string(item, "spec_ref"),
                    source_domains=_domains(item.get("source_domains", ())),
                    target_domains=_domains(item.get("target_domains", ())),
                    target_domains_excluded=_domains(item.get("target_domains_excluded", ())),
                    source_artifact_types=_strings(item.get("source_artifact_types", ())),
                    source_artifact_types_excluded=_strings(item.get("source_artifact_types_excluded", ())),
                    intermediate_artifact_types=_strings(item.get("intermediate_artifact_types", ())),
                    source_passive=_optional_bool(item.get("source_passive")),
                    target_passive=_optional_bool(item.get("target_passive")),
                    connection_artifact_types=_strings(item.get("connection_artifact_types", ())),
                    allowed_connection_artifact_types=_strings(item.get("allowed_connection_artifact_types", ())),
                    intermediate_domain_must_match_endpoint=_bool(
                        item.get("intermediate_domain_must_match_endpoint", False)
                    ),
                    intermediate_domain_exception=_bool(item.get("intermediate_domain_exception", False)),
                    always_disallow=_bool(item.get("always_disallow", False)),
                )
            )
        except KeyError as exc:
            raise ValueError(f"relationship derivation restriction misses {exc.args[0]!r}") from exc
    return tuple(rules)


def permits_derived_relationship(
    source: EntityTypeInfo,
    target: EntityTypeInfo,
    connection: ConnectionTypeInfo,
    intermediate: EntityTypeInfo,
    rules: tuple[DerivationRestriction, ...],
) -> bool:
    """Return whether all supplied restrictions admit a derived relationship."""
    source_domain = derivation_domain(source)
    target_domain = derivation_domain(target)
    intermediate_domain = derivation_domain(intermediate)
    for rule in rules:
        if _matches(rule, source, target, connection, intermediate, source_domain, target_domain, intermediate_domain):
            if rule.always_disallow or connection.artifact_type not in rule.allowed_connection_artifact_types:
                return False
    return True


def _matches(
    rule: DerivationRestriction,
    source: EntityTypeInfo,
    target: EntityTypeInfo,
    connection: ConnectionTypeInfo,
    intermediate: EntityTypeInfo,
    source_domain: DerivationDomain,
    target_domain: DerivationDomain,
    intermediate_domain: DerivationDomain,
) -> bool:
    if rule.source_domains and source_domain not in rule.source_domains:
        return False
    if rule.target_domains and target_domain not in rule.target_domains:
        return False
    if rule.target_domains_excluded and target_domain in rule.target_domains_excluded:
        return False
    if rule.source_artifact_types and source.artifact_type not in rule.source_artifact_types:
        return False
    if rule.source_artifact_types_excluded and source.artifact_type in rule.source_artifact_types_excluded:
        return False
    if rule.intermediate_artifact_types and intermediate.artifact_type not in rule.intermediate_artifact_types:
        return False
    if rule.source_passive is not None and _is_passive(source) != rule.source_passive:
        return False
    if rule.target_passive is not None and _is_passive(target) != rule.target_passive:
        return False
    if rule.connection_artifact_types and connection.artifact_type not in rule.connection_artifact_types:
        return False
    # The domain-matching clause presupposes an intermediate that *has* a domain to compare. A
    # junction does not: it stands for the relationship itself, and its derivation domain is
    # `relationships` precisely for that reason — which never equals an endpoint's domain, so the
    # clause disallowed every junction-mediated derivation. That made a junction a dead end for
    # impact analysis and reported a requirement realized through an AND-junction as unrealized,
    # while the eligible-realizer set excludes junctions as helpers, so nothing could stand in.
    if (
        rule.intermediate_domain_must_match_endpoint
        and "junction" not in intermediate.classes
        and intermediate_domain not in {source_domain, target_domain}
    ):
        if not (
            rule.intermediate_domain_exception
            and source_domain == "implementation_migration"
            and intermediate_domain == "core"
            and target_domain in {"motivation", "strategy"}
        ):
            return True
        return False
    if rule.intermediate_domain_must_match_endpoint:
        return False
    return True


def _is_passive(info: EntityTypeInfo) -> bool:
    return "passive-structure-element" in info.classes


def _required_string(item: Mapping[object, object], key: str) -> str:
    value = item[key]
    if not isinstance(value, str):
        raise ValueError(f"relationship derivation restriction {key} must be a string")
    return value


def _strings(value: object) -> frozenset[str]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or not all(isinstance(item, str) for item in value)
    ):
        raise ValueError("relationship derivation restriction values must be string sequences")
    return frozenset(value)


def _domains(value: object) -> frozenset[DerivationDomain]:
    values = _strings(value)
    allowed = frozenset({"motivation", "strategy", "core", "implementation_migration", "relationships"})
    if not values <= allowed:
        raise ValueError("unknown relationship derivation domain")
    return frozenset(cast(DerivationDomain, value) for value in values)


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    return _bool(value)


def _bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("relationship derivation restriction flag must be a boolean")
    return value

"""Declarative pairwise relationship-composition rules."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, cast

from src.domain.relationships.relationship_derivation_restrictions import (
    DerivationRestriction,
    restriction_rules_from_mapping,
)
from src.domain.yaml_documents import parse_yaml

Certainty = Literal["certain", "potential"]
Join = Literal["target-source", "target-target", "source-source", "source-target"]
Endpoint = Literal["first-source", "first-target", "second-source", "second-target"]
_CERTAINTIES = frozenset({"certain", "potential"})
_JOINS = frozenset({"target-source", "target-target", "source-source", "source-target"})
_ENDPOINTS = frozenset({"first-source", "first-target", "second-source", "second-target"})
_RESULTS = frozenset({"first", "second", "weakest", "specialization", "triggering", "flow"})


@dataclass(frozen=True)
class CompositionRule:
    """One source-specification rule, identified only through traceability metadata."""

    spec_ref: str
    certainty: Certainty
    first_role: str
    second_role: str
    result: Literal["first", "second", "weakest", "specialization", "triggering", "flow"]
    join: Join = "target-source"
    result_source: Endpoint = "first-source"
    result_target: Endpoint = "second-target"
    first_artifact_type: str | None = None
    second_artifact_type: str | None = None
    second_artifact_types: tuple[str, ...] = ()
    intermediate_artifact_type: str | None = None
    intermediate_class: str | None = None
    """Match the intermediate by ontology *class* rather than artifact type — for a family whose
    members compose identically. `junction` is the case: `and-junction` and `or-junction` differ in
    what the combination means, never in how a relationship passes through."""
    excluded_intermediate_classes: frozenset[str] = frozenset()
    """Intermediate classes this rule does NOT compose across, computed at load (see
    `_with_class_exclusivity`) rather than written per row: a class some rule claims by name is a class
    the generic rules do not cover. Nothing in the evaluator names a class; the spec does."""
    requires_same_connection_type: bool = False
    """Both legs must carry the SAME relationship type. A junction joins relationships of one type, so
    a mismatch is a modelling error rather than a chain — deriving a weakest-of would launder it."""
    requires_permitted_result: bool = False


def composition_rules_from_mapping(raw: object) -> tuple[CompositionRule, ...]:
    """Validate ontology-supplied relationship composition data."""
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ValueError("relationship derivation rules must be a sequence")
    rules: list[CompositionRule] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("relationship derivation rule must be a mapping")
        try:
            certainty = str(item["certainty"])
            result = str(item["result"])
            join = str(item.get("join", "target-source"))
            result_source = str(item.get("result_source", "first-source"))
            result_target = str(item.get("result_target", "second-target"))
            if certainty not in _CERTAINTIES:
                raise ValueError(f"unknown derivation certainty {certainty!r}")
            if result not in _RESULTS:
                raise ValueError(f"unknown derivation result selector {result!r}")
            if join not in _JOINS:
                raise ValueError(f"unknown derivation join {join!r}")
            if result_source not in _ENDPOINTS or result_target not in _ENDPOINTS:
                raise ValueError("unknown derivation result endpoint")
            rules.append(
                CompositionRule(
                    spec_ref=str(item["spec_ref"]),
                    certainty=cast(Certainty, certainty),
                    first_role=str(item["first_role"]),
                    second_role=str(item["second_role"]),
                    result=cast(Literal["first", "second", "weakest", "specialization", "triggering", "flow"], result),
                    join=cast(Join, join),
                    result_source=cast(Endpoint, result_source),
                    result_target=cast(Endpoint, result_target),
                    first_artifact_type=_optional_string(item.get("first_artifact_type")),
                    second_artifact_type=_optional_string(item.get("second_artifact_type")),
                    second_artifact_types=_string_sequence(item.get("second_artifact_types", ())),
                    intermediate_artifact_type=_optional_string(item.get("intermediate_artifact_type")),
                    intermediate_class=_optional_string(item.get("intermediate_class")),
                    requires_same_connection_type=_optional_bool(
                        item.get("requires_same_connection_type", False)
                    ),
                    requires_permitted_result=_optional_bool(item.get("requires_permitted_result", False)),
                )
            )
        except KeyError as exc:
            raise ValueError(f"relationship derivation rule misses {exc.args[0]!r}") from exc
    return _with_class_exclusivity(tuple(rules))


def _with_class_exclusivity(rules: tuple[CompositionRule, ...]) -> tuple[CompositionRule, ...]:
    """A class a rule claims by name is a class the generic rules must not compose across.

    Derived from the data rather than written onto all thirty-odd generic rows — and rather than named
    in the evaluator, which is what the first cut of junction derivation did (`if "junction" in
    intermediate.classes`, with the ontology silent about it). The fact belongs to the spec, as
    `intermediate_class: junction` on the junction rules; this states its consequence once.

    Without the consequence, un-refusing junctions lets the ordinary chain rules at them: `assignment`
    then `serving` across a junction composes into a serving the model never stated.
    """
    claimed = frozenset(rule.intermediate_class for rule in rules if rule.intermediate_class is not None)
    if not claimed:
        return rules
    return tuple(
        rule if rule.intermediate_class is not None else replace(rule, excluded_intermediate_classes=claimed)
        for rule in rules
    )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("relationship derivation artifact type must be a string")
    return value


def _string_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("relationship derivation artifact types must be a sequence")
    if not all(isinstance(item, str) for item in value):
        raise ValueError("relationship derivation artifact types must be strings")
    return tuple(value)


def _optional_bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("relationship derivation permitted-result flag must be a boolean")
    return value


def load_composition_rules(package_dir: Path) -> tuple[CompositionRule, ...]:
    """Load an ontology's optional declarative relationship-composition rules."""
    path = package_dir / "relationship_derivation.yaml"
    if not path.is_file():
        return ()
    with path.open(encoding="utf-8") as stream:
        raw: object = parse_yaml(stream) or {}
    if not isinstance(raw, Mapping):
        raise ValueError("relationship derivation data must be a mapping")
    return composition_rules_from_mapping(raw.get("composition_rules", ()))


def load_derivation_restrictions(package_dir: Path) -> tuple[DerivationRestriction, ...]:
    """Load an ontology's optional declarative relationship restrictions."""
    path = package_dir / "relationship_derivation.yaml"
    if not path.is_file():
        return ()
    with path.open(encoding="utf-8") as stream:
        raw: object = parse_yaml(stream) or {}
    if not isinstance(raw, Mapping):
        raise ValueError("relationship derivation data must be a mapping")
    return restriction_rules_from_mapping(raw.get("restrictions", ()))

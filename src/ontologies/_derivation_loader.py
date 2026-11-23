"""Read the optional derivation declaration for one ontology."""

from collections.abc import Mapping
from pathlib import Path

from src.domain.relationships.relationship_derivation_restrictions import (
    DerivationRestriction,
    restriction_rules_from_mapping,
)
from src.domain.relationships.relationship_derivation_rules import CompositionRule, composition_rules_from_mapping
from src.domain.yaml_documents import parse_yaml


def load_derivation(package_dir: Path) -> tuple[tuple[CompositionRule, ...], tuple[DerivationRestriction, ...]]:
    path = package_dir / "relationship_derivation.yaml"
    if not path.is_file():
        return (), ()
    with path.open(encoding="utf-8") as stream:
        raw: object = parse_yaml(stream) or {}
    if not isinstance(raw, Mapping):
        raise ValueError("relationship derivation data must be a mapping")
    return (
        composition_rules_from_mapping(raw.get("composition_rules", ())),
        restriction_rules_from_mapping(raw.get("restrictions", ())),
    )

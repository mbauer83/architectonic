"""Relationship-derivation metadata loaded from the ArchiMate connection catalog."""

from __future__ import annotations

from copy import deepcopy

import pytest
import yaml  # type: ignore[import-untyped]

from src.ontologies.archimate_4._loader import _PACKAGE_DIR
from src.ontologies.archimate_4._yaml_data import load_connection_types

_EXPECTED: dict[str, tuple[str, int | None]] = {
    "archimate-composition": ("structural", 4),
    "archimate-aggregation": ("structural", 3),
    "archimate-assignment": ("structural", 2),
    "archimate-realization": ("structural", 1),
    "archimate-serving": ("dependency", 4),
    "archimate-access": ("dependency", 3),
    "archimate-influence": ("dependency", 2),
    "archimate-association": ("dependency", 1),
    "archimate-triggering": ("dynamic", None),
    "archimate-flow": ("dynamic", None),
    "archimate-specialization": ("specialization", None),
}


def _catalog_data() -> dict[str, object]:
    raw = yaml.safe_load((_PACKAGE_DIR / "connections.yaml").read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def test_archimate_relationships_have_the_specification_classification() -> None:
    connections = load_connection_types(_catalog_data())

    actual = {
        name: (info.derivation_role, info.derivation_strength)
        for name, info in connections.items()
        if name in _EXPECTED
    }
    assert actual == _EXPECTED


def test_types_without_derivation_metadata_opt_out() -> None:
    connections = load_connection_types(_catalog_data())

    assert connections["sequence-synchronous"].derivation_role is None
    assert connections["sequence-synchronous"].derivation_strength is None


@pytest.mark.parametrize(
    ("derivation", "message"),
    [
        ({"role": "unknown"}, "unknown derivation role"),
        ({"role": "structural"}, "requires an integer strength"),
        ({"role": "dependency", "strength": "4"}, "requires an integer strength"),
        ({"role": "dynamic", "strength": 1}, "forbids strength"),
        ({"role": "specialization", "strength": 1}, "forbids strength"),
    ],
)
def test_invalid_derivation_metadata_is_rejected(derivation: object, message: str) -> None:
    data = deepcopy(_catalog_data())
    connection_types = data["connection_types"]
    assert isinstance(connection_types, dict)
    archimate = connection_types["archimate"]
    assert isinstance(archimate, dict)
    composition = archimate["archimate-composition"]
    assert isinstance(composition, dict)
    composition["derivation"] = derivation

    with pytest.raises(ValueError, match=message):
        load_connection_types(data)


def test_strengths_must_be_unique_within_a_derivation_role() -> None:
    data = deepcopy(_catalog_data())
    connection_types = data["connection_types"]
    assert isinstance(connection_types, dict)
    archimate = connection_types["archimate"]
    assert isinstance(archimate, dict)
    assignment = archimate["archimate-assignment"]
    assert isinstance(assignment, dict)
    assignment["derivation"] = {"role": "structural", "strength": 4}

    with pytest.raises(ValueError, match="duplicate derivation strength"):
        load_connection_types(data)

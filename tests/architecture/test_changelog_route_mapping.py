"""The published route map is complete against the migration ledger.

A breaking release's value to a consumer is the mapping, and a mapping that is *nearly* complete is
worse than none: the one row that is missing is the one a consumer discovers as a 404 in production.
So the table is checked against the ledger rather than maintained by hand and hoped over.

The table lives in ``changelog-assets/`` rather than in ``CHANGELOG.md``: it is 79 rows of lookup, and
a changelog a reader does not finish is a changelog that did not warn them. Outside ``docs/`` on
purpose — every route it names is *retired*, and the documentation-claims check asserts that a
documented endpoint is a served one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.infrastructure.rest.route_policy import BY_OPERATION, RETIRED_ROUTES

_ROUTE_MAP = Path(__file__).resolve().parents[2] / "changelog-assets" / "0.2.0-route-map.md"

_ROW = re.compile(r"^\|\s*`([A-Z]+ [^`]+)`\s*\|\s*`([A-Z]+ [^`]+)`\s*\|\s*$", re.MULTILINE)


@pytest.fixture(scope="module")
def documented_mapping() -> dict[str, str]:
    return dict(_ROW.findall(_ROUTE_MAP.read_text(encoding="utf-8")))


def _expected_mapping() -> dict[str, str]:
    return {
        f"{method} {template}": f"{BY_OPERATION[operation].method} {BY_OPERATION[operation].template}"
        for (method, template), operation in RETIRED_ROUTES.items()
    }


def test_every_retired_route_is_documented_with_its_replacement(
    documented_mapping: dict[str, str],
) -> None:
    expected = _expected_mapping()
    missing = {old: new for old, new in expected.items() if old not in documented_mapping}
    assert missing == {}, f"retired routes absent from the published route map: {sorted(missing)}"


def test_the_documented_mapping_points_where_the_manifest_does(
    documented_mapping: dict[str, str],
) -> None:
    expected = _expected_mapping()
    wrong = {
        old: (documented, expected[old])
        for old, documented in documented_mapping.items()
        if old in expected and documented != expected[old]
    }
    assert wrong == {}, f"the route map disagrees with the manifest: {wrong}"


def test_the_documented_mapping_invents_nothing(documented_mapping: dict[str, str]) -> None:
    """A row for a route that was never retired sends a consumer to change working code."""
    expected = _expected_mapping()
    invented = sorted(set(documented_mapping) - set(expected))
    assert invented == [], f"the route map documents routes that are not retired: {invented}"

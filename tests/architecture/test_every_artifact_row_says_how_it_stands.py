"""Every REST payload that says whether an artifact is global also says how it stands.

`is_global` is the measured failure this guards against. One predicate, one owner — and the decision
to *emit* it spelled at ten sites in seven modules, with the three hit serialisers disagreeing:
`_search_hits.py` emits it, `entities/search.py` and the MCP return do not. That is type-legal,
because the contract declares `is_global: bool | None = None`, so a reader cannot tell "not global"
from "nobody said".

`baseline_standing` must not go the same way, and for it the stakes are higher: absence reads as the
enterprise baseline, which is exactly the reading that makes a pending local change invisible. A
surface that quietly stops reporting one shows an artifact as accepted upstream when it is not.

**The two are paired deliberately.** `is_global` marks the places a payload describes one artifact's
standing in the tier system — which is the same set of places that must report its standing against
the baseline. Pinning the pair means the register is derived from the code rather than maintained by
hand: an eleventh row added anywhere fails here until it carries both.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.support.source_paths import REPO_ROOT

REST = REPO_ROOT / "src" / "infrastructure" / "rest"

#: The payload keys. Read from the domain rather than spelled, so a rename moves this with it.
GLOBAL_KEY = "is_global"
STANDING_KEY = "baseline_standing"


def _rest_sources() -> list[Path]:
    return sorted(p for p in REST.rglob("*.py") if p.name != "__init__.py")


def _emits(source: str, key: str) -> int:
    """How many times this module writes `key` into a payload — as a dict entry or a subscript set.

    Counted from the syntax tree rather than by substring, so the key appearing in a docstring or a
    comment is not mistaken for a surface emitting it.
    """
    tree = ast.parse(source)
    found = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            found += sum(
                1 for k in node.keys
                if isinstance(k, ast.Constant) and k.value == key
            )
        elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            if node.slice.value == key and isinstance(getattr(node, "ctx", None), ast.Store):
                found += 1
    return found


def _named_constant_emissions(source: str, constant: str) -> int:
    """Emissions written through the shared constant rather than a literal."""
    tree = ast.parse(source)
    found = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            found += sum(1 for k in node.keys if isinstance(k, ast.Name) and k.id == constant)
        elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Name):
            if node.slice.id == constant and isinstance(getattr(node, "ctx", None), ast.Store):
                found += 1
    return found


def _standing_emissions(source: str) -> int:
    return _emits(source, STANDING_KEY) + _named_constant_emissions(source, "BASELINE_STANDING")


@pytest.fixture(scope="module")
def rows() -> dict[str, tuple[int, int]]:
    """`module -> (is_global emissions, baseline_standing emissions)` for every module emitting either."""
    found: dict[str, tuple[int, int]] = {}
    for path in _rest_sources():
        source = path.read_text(encoding="utf-8")
        globals_, standings = _emits(source, GLOBAL_KEY), _standing_emissions(source)
        if globals_ or standings:
            found[str(path.relative_to(REPO_ROOT))] = (globals_, standings)
    return found


def test_the_scan_finds_the_surfaces_at_all(rows: dict[str, tuple[int, int]]) -> None:
    """Precondition: a scan that matched nothing would make the assertion below vacuous."""
    assert len(rows) >= 5, rows
    assert sum(g for g, _ in rows.values()) >= 8, rows


def test_no_module_says_whether_an_artifact_is_global_without_saying_how_it_stands(
    rows: dict[str, tuple[int, int]],
) -> None:
    silent = {module: counts for module, counts in rows.items() if counts[0] and not counts[1]}

    assert silent == {}, (
        "these describe an artifact's place in the tier system and say nothing about pending local "
        f"changes to it, so a proposed artifact reads there as accepted: {silent}. Emit "
        f"`{STANDING_KEY}` beside `{GLOBAL_KEY}`, from `state.baseline_standing_reader()`."
    )


def test_a_module_says_how_it_stands_at_least_as_often_as_whether_it_is_global(
    rows: dict[str, tuple[int, int]],
) -> None:
    """A module with two payload shapes must carry it in both, not in whichever was edited.

    Counting rather than merely requiring one occurrence: `documents.py` builds a list row and a
    detail, and a fix applied to one of them is the shape of the original defect, not a fix.

    **At least, not exactly.** More is right and was measured: `reference-search` builds hits in
    three branches and only the entity branch reported `is_global` at all, so the diagram and
    document hits now say how they stand while saying nothing about tier. Requiring equality would
    have demanded the *fewer* of the two.
    """
    short = {
        module: {"is_global": g, "baseline_standing": s}
        for module, (g, s) in rows.items()
        if g and s < g
    }

    assert short == {}, (
        f"one payload in these modules says how it stands and another does not: {short}"
    )


def test_the_wire_contract_does_not_permit_omission() -> None:
    """The half `is_global` got wrong: optional on the contract, so omission is type-legal."""
    from src.infrastructure.rest.contracts.baseline_standing import BaselineStandingContract  # noqa: F401
    from src.infrastructure.rest.contracts.entities import EntitySummary

    field = EntitySummary.model_fields[STANDING_KEY]

    assert field.is_required(), (
        f"{STANDING_KEY} is optional on EntitySummary, which is how `is_global` came to be omitted "
        "by two of three serialisers with nothing failing"
    )

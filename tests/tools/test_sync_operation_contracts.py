"""Each sync contract, held against the returns of the handler that serves it.

The third application of one guard. A closed DTO that renames or omits what its handler returns
rejects every real response, and the manifest naming *one* contract for four unrelated outcomes hid
that: `ok` is the only field all four share, so a single model would have declared seven optionals and
promised nothing about which to read.

So there are four contracts, and this pins each to its handler's own returns. Read from source rather
than by driving the routes: each needs a git repository in a particular state, and the question is
which shapes the handler *can* return — a property of the code, not of any one fixture.
"""

from __future__ import annotations

import ast
import pathlib

from src.infrastructure.rest.contracts.sync import (
    EngagementSaveResponse,
    EnterpriseSaveResponse,
    EnterpriseSubmitResponse,
    EnterpriseWithdrawResponse,
)

_SYNC = (
    pathlib.Path(__file__).resolve().parents[2]
    / "src" / "infrastructure" / "rest" / "routers" / "sync.py"
)

#: Handler name → the contract it declares.
_CONTRACTS = {
    "save_engagement": EngagementSaveResponse,
    "save_enterprise": EnterpriseSaveResponse,
    "submit_enterprise": EnterpriseSubmitResponse,
    "withdraw_enterprise": EnterpriseWithdrawResponse,
}


def _returned_key_sets(handler: str) -> list[frozenset[str]]:
    """Every dict literal ``handler`` returns, as its set of keys.

    A handler may return more than one shape — ``submit_enterprise`` reports an existing pending
    branch differently from one it just pushed — and both are part of the contract.
    """
    tree = ast.parse(_SYNC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef) and node.name == handler:
            return [
                frozenset(
                    key.value for key in inner.value.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                )
                for inner in ast.walk(node)
                if isinstance(inner, ast.Return) and isinstance(inner.value, ast.Dict)
            ]
    raise AssertionError(f"no handler named {handler!r} in {_SYNC}")


def test_every_handler_returns_at_least_one_shape() -> None:
    """Guards the guard: an extraction that found nothing would make every assertion below vacuous."""
    for handler in _CONTRACTS:
        assert _returned_key_sets(handler), f"{handler} returns no dict literal"


def test_each_contract_declares_every_field_its_handler_emits() -> None:
    """A key the handler emits and the contract omits is a rejected response: the models are closed."""
    for handler, contract in _CONTRACTS.items():
        emitted = set().union(*_returned_key_sets(handler))
        declared = set(contract.model_fields)
        assert emitted <= declared, (
            f"{handler} emits fields {contract.__name__} omits: {sorted(emitted - declared)}"
        )


def test_each_contract_invents_no_field_its_handler_never_emits() -> None:
    """The other direction, and the one that costs a 500 rather than a missing key."""
    for handler, contract in _CONTRACTS.items():
        emitted = set().union(*_returned_key_sets(handler))
        declared = set(contract.model_fields)
        assert declared <= emitted, (
            f"{contract.__name__} declares fields {handler} never returns: {sorted(declared - emitted)}"
        )


def test_a_field_only_some_shapes_carry_is_optional() -> None:
    """``submit_enterprise`` answers differently for an already-pending branch. A field present in one
    shape and not the other cannot be required, or the other shape fails its own contract."""
    for handler, contract in _CONTRACTS.items():
        shapes = _returned_key_sets(handler)
        always = frozenset.intersection(*shapes)
        required = {name for name, f in contract.model_fields.items() if f.is_required()}
        assert required == always, (
            f"{contract.__name__} requires {sorted(required)} but {handler} always emits "
            f"{sorted(always)}"
        )


def test_the_four_contracts_are_distinct_shapes() -> None:
    """Why there are four and not the one the manifest first named: if these collapsed to the same
    field set, one contract would have been right and this split would be noise."""
    shapes = {name: frozenset(c.model_fields) for name, c in
              ((c.__name__, c) for c in _CONTRACTS.values())}
    assert len(set(shapes.values())) == len(shapes), f"contracts share a field set: {shapes}"
    # And `ok` really is all they have in common — the reason a single model would promise nothing.
    assert frozenset.intersection(*shapes.values()) == frozenset({"ok"})


def test_a_real_response_from_each_handler_validates() -> None:
    """Field sets agreeing is necessary, not sufficient: the types have to agree too."""
    assert EngagementSaveResponse.model_validate(
        {"ok": True, "commit": "abc123", "pushed": True, "message": "save"}
    ).pushed is True
    assert EnterpriseSaveResponse.model_validate(
        {"ok": True, "commit": "def456", "message": "work"}
    ).commit == "def456"
    first = EnterpriseSubmitResponse.model_validate({"ok": True, "branch": "review/x"})
    assert first.already_submitted is None, "absent on a first submission, so its presence is a signal"
    again = EnterpriseSubmitResponse.model_validate(
        {"ok": True, "already_submitted": True, "branch": "review/x", "pushed_at": "2026-07-31T00:00:00Z"}
    )
    assert again.already_submitted is True
    assert EnterpriseWithdrawResponse.model_validate(
        {"ok": True, "discarded_branch": "review/x"}
    ).discarded_branch == "review/x"

"""The only sanctioned way past the age floor, and the reason it cannot quietly become permanent.

The two controls can give opposite instructions: when the only fix for a known vulnerability was
published an hour ago, the age floor says wait and the vulnerability gate says take it. Without a
named way through, a control gets disabled — and that is invisible in a way a dated register entry
is not.

So each entry names one package at one version, says why, and states the day it stops applying. What
is pinned here is that none of those can be skipped, that a spent entry admits nothing, and that a
spent entry keeps failing the gate until it is removed.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from tools.supplychain import check_supply_chain
from tools.supplychain.emergency_exceptions import (
    MAX_LIFETIME,
    REGISTER,
    EmergencyException,
    expired,
)
from tools.supplychain.release_age import (
    FLOOR,
    Admitted,
    LockedPackage,
    Refused,
    RegistryArtifacts,
    judge,
    vcs_ref,
)

_NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
_TODAY = _NOW.date()
_WORKSPACE = Path("/workspace/project")

_WHY = "the only fix for a known vulnerability was published inside the floor; see the advisory"


def _exception(**overrides: object) -> EmergencyException:
    fields: dict[str, object] = {
        "package": "urgent", "version": "1.2.3",
        "declared": _TODAY, "expires": _TODAY + timedelta(days=7),
        "justification": _WHY,
    }
    return EmergencyException(**{**fields, **overrides})  # type: ignore[arg-type]


def _fresh_pin(name: str = "urgent", version: str = "1.2.3") -> LockedPackage:
    return LockedPackage(
        name=name, version=version,
        source=RegistryArtifacts(uploaded=(_NOW - timedelta(hours=1),)),
    )


def _verdict(package: LockedPackage, register: tuple[EmergencyException, ...]) -> object:
    return judge(package, now=_NOW, workspace=_WORKSPACE, register=register)


def test_an_unexpired_exception_admits_the_pin_it_names() -> None:
    verdict = _verdict(_fresh_pin(), (_exception(),))
    assert isinstance(verdict, Admitted)
    assert _WHY in verdict.reason


def test_it_admits_only_the_version_it_names() -> None:
    assert isinstance(_verdict(_fresh_pin(version="1.2.4"), (_exception(),)), Refused)


def test_an_expired_exception_admits_nothing() -> None:
    spent = _exception(declared=_TODAY - timedelta(days=20), expires=_TODAY - timedelta(days=1))
    assert isinstance(_verdict(_fresh_pin(), (spent,)), Refused)


def test_the_day_it_expires_is_already_too_late() -> None:
    """The boundary, decided: an entry expiring today no longer admits today."""
    lapsing = _exception(declared=_TODAY - timedelta(days=3), expires=_TODAY)
    assert isinstance(_verdict(_fresh_pin(), (lapsing,)), Refused)
    assert expired((lapsing,), on=_TODAY) == (lapsing,)


def test_it_never_reaches_a_version_control_pin() -> None:
    """Refused outright, not by paperwork: over a permanent git pin this becomes a scheduled break."""
    pinned = LockedPackage(
        name="urgent", version="1.2.3", source=vcs_ref("https://example.invalid/p.git#" + "b" * 40)
    )
    assert isinstance(_verdict(pinned, (_exception(),)), Refused)


@pytest.mark.parametrize(
    "overrides, why",
    [
        ({"package": ""}, "no package"),
        ({"version": ""}, "no version"),
        ({"expires": _TODAY}, "expires the day it was declared"),
        ({"expires": _TODAY + MAX_LIFETIME + timedelta(days=1)}, "outlasts the maximum"),
        ({"justification": "temporary"}, "says nothing"),
    ],
)
def test_a_malformed_exception_cannot_be_constructed(overrides: dict[str, object], why: str) -> None:
    """Refused at construction, so it cannot be committed and found by a gate later."""
    with pytest.raises(ValueError):
        _exception(**overrides)
    assert why


def test_a_spent_entry_fails_the_gate_even_when_every_pin_has_aged_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Otherwise a register accumulates entries that changed nothing, and nobody reads it."""
    spent = _exception(declared=_TODAY - timedelta(days=20), expires=_TODAY - timedelta(days=1))
    assert check_supply_chain._spent_exceptions(_NOW) == [], "the committed register is not empty"

    monkeypatch.setattr(check_supply_chain, "REGISTER", (spent,))
    reported = check_supply_chain._spent_exceptions(_NOW)
    assert len(reported) == 1
    assert "expired" in reported[0] and spent.package in reported[0]


def test_every_entry_in_force_is_well_formed_and_unspent() -> None:
    """The standing gate over the committed register, whatever it holds."""
    assert expired(REGISTER, on=date.today()) == ()
    for entry in REGISTER:
        assert entry.expires - entry.declared <= MAX_LIFETIME


def test_the_floor_the_exception_waives_is_the_one_the_gate_enforces() -> None:
    assert FLOOR == timedelta(hours=24)

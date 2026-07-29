"""Every assurance verifier code must denote exactly one rule.

A code that names two rules cannot be cited, suppressed or documented unambiguously, and it
silently blocks the next code allocation — `E504` denoted both the dangling-endpoint rule and
the risk-treatment rule for exactly that reason. Codes are declared in one catalogue and rules
take their code from it, so these tests check the catalogue rather than a docstring that could
drift from the rules it describes.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

from src.application.verification import assurance_findings as catalogue
from src.application.verification.assurance_findings import (
    ACCEPTED_RISK_IS_NOT_THE_WHOLE_ANSWER,
    ASSURANCE_FINDING_KINDS,
    EDGE_ENDPOINTS_RESOLVE,
)

_VERIFICATION_PACKAGE = Path(catalogue.__file__).parent


def _rule_modules() -> list[Path]:
    return sorted(
        path for path in _VERIFICATION_PACKAGE.glob("*assurance*.py")
        if path.name != "assurance_findings.py"
    )


def _kinds_referenced_by_function() -> dict[str, set[str]]:
    """Catalogue member name → the rule functions that construct an issue from it."""
    known = {name for name, value in vars(catalogue).items() if isinstance(value, catalogue.AssuranceFindingKind)}
    by_kind: dict[str, set[str]] = {}
    for module_path in _rule_modules():
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef):
                continue
            for name in ast.walk(function):
                if isinstance(name, ast.Name) and name.id in known:
                    by_kind.setdefault(name.id, set()).add(f"{module_path.stem}.{function.name}")
    return by_kind


def test_no_code_is_allocated_twice() -> None:
    duplicates = [code for code, count in Counter(k.code for k in ASSURANCE_FINDING_KINDS).items() if count > 1]

    assert not duplicates, f"codes allocated to more than one rule: {duplicates}"


def test_every_declared_kind_appears_in_the_catalogue() -> None:
    """A kind left out of the tuple is invisible to every check that iterates it."""
    declared = {
        value for value in vars(catalogue).values() if isinstance(value, catalogue.AssuranceFindingKind)
    }

    assert declared == set(ASSURANCE_FINDING_KINDS)


def test_each_kind_is_emitted_by_one_rule() -> None:
    shared = {kind: sorted(fns) for kind, fns in _kinds_referenced_by_function().items() if len(fns) > 1}

    assert not shared, f"catalogue entries emitted by more than one rule: {shared}"


def test_every_catalogued_kind_is_actually_used() -> None:
    """A code nobody emits is an allocation nobody can trigger."""
    used = set(_kinds_referenced_by_function())
    declared = {name for name, value in vars(catalogue).items() if isinstance(value, catalogue.AssuranceFindingKind)}

    assert declared - used == set(), f"allocated but never emitted: {sorted(declared - used)}"


def test_severity_is_carried_by_the_code_rather_than_the_call_site() -> None:
    """A hard finding blocks sign-off, so the distinction must not vary by where it is raised.

    The prefix fixes whether a finding blocks: `E` always does, `W` never does. Within the
    non-blocking ones the severity separates a defect from a coverage statement — `warning` for
    something wrong, `info` for something merely not done yet — because a rule that reports work
    outstanding on every run would otherwise have to shout, and a verifier that always shouts stops
    being read.
    """
    for kind in ASSURANCE_FINDING_KINDS:
        if kind.code.startswith("E"):
            assert kind.severity == "error", kind.code
        else:
            assert kind.severity in ("warning", "info"), kind.code


def test_the_dangling_endpoint_rule_keeps_the_older_code() -> None:
    """Of the two rules that shared E504, the more-referenced one kept it."""
    assert EDGE_ENDPOINTS_RESOLVE.code == "E504"
    assert ACCEPTED_RISK_IS_NOT_THE_WHOLE_ANSWER.code == "E506"

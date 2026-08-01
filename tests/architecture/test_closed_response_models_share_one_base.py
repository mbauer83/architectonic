"""A response contract declares closedness by inheriting it, not by restating it.

``extra="forbid"`` is this package's central convention and it was written out twenty-six times, once
per module, as a byte-identical private ``_Closed`` base. Nothing held the copies equal, and the
package was inconsistent about its own rule while the other half of it —
:class:`wire_nulls.NullsOmitted` — lived once with its rationale and was imported everywhere.
:class:`wire_shape.Closed` is that half, in the same shape; this test is what keeps it single.

**Scope: the response contracts.** Request bodies under ``rest/routers/`` also declare
``extra="forbid"``, for a reason of their own that is written down where they are — a body carrying
an identity field that is already in the path is rejected rather than ignored. They are not response
DTOs, they are not served, and folding them in here would make one base answer two questions.
"""

from __future__ import annotations

import ast
from pathlib import Path

from pydantic import BaseModel

from src.infrastructure.rest.contracts.wire_nulls import NullsOmitted
from src.infrastructure.rest.contracts.wire_shape import Closed

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTRACTS = _REPO_ROOT / "src/infrastructure/rest/contracts"

#: The module that defines the base, and the one that composes the null policy onto it.
_MAY_SET_THE_CONFIG = {"wire_shape.py", "wire_nulls.py"}


def _forbidding_classes(tree: ast.Module) -> list[str]:
    """Classes whose own body sets ``extra="forbid"`` in a ``model_config``."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for statement in node.body:
            if not isinstance(statement, ast.Assign):
                continue
            names = [t.id for t in statement.targets if isinstance(t, ast.Name)]
            if "model_config" not in names or not isinstance(statement.value, ast.Call):
                continue
            for keyword in statement.value.keywords:
                if keyword.arg == "extra" and getattr(keyword.value, "value", None) == "forbid":
                    found.append(node.name)
    return found


def test_no_response_contract_module_declares_its_own_closed_base() -> None:
    offenders = {}
    for path in sorted(_CONTRACTS.glob("*.py")):
        if path.name in _MAY_SET_THE_CONFIG:
            continue
        classes = _forbidding_classes(ast.parse(path.read_text(encoding="utf-8")))
        if classes:
            offenders[path.name] = classes
    assert offenders == {}, (
        "These modules restate `extra=\"forbid\"` instead of inheriting "
        "`contracts.wire_shape.Closed` (or `NullsOmitted`, which composes it): "
        f"{offenders}"
    )


def test_the_two_bases_compose_rather_than_repeat() -> None:
    assert issubclass(NullsOmitted, Closed)
    # The point of the composition: closedness is inherited, not restated, and still applies.
    assert NullsOmitted.model_config.get("extra") == "forbid"
    assert "extra" not in ast_config_keys("wire_nulls.py", "NullsOmitted")


def ast_config_keys(module: str, class_name: str) -> set[str]:
    """The ``model_config`` keywords a class sets in its *own* body."""
    tree = ast.parse((_CONTRACTS / module).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for statement in node.body:
                if (
                    isinstance(statement, ast.Assign)
                    and any(t.id == "model_config" for t in statement.targets if isinstance(t, ast.Name))
                    and isinstance(statement.value, ast.Call)
                ):
                    return {k.arg for k in statement.value.keywords if k.arg is not None}
    raise AssertionError(f"{class_name} not found in {module}")


def test_the_scanner_reads_the_declaration_it_is_looking_for() -> None:
    # Without this, an AST walk that stopped matching would report zero offenders over an empty scan.
    assert _forbidding_classes(ast.parse((_CONTRACTS / "wire_shape.py").read_text())) == ["Closed"]
    assert _forbidding_classes(ast.parse("class A(BaseModel):\n    x: int\n")) == []
    assert len(list(_CONTRACTS.glob("*.py"))) > 20


def test_every_closed_response_contract_actually_forbids_extras() -> None:
    # The base is only worth sharing if it still does the thing. One representative from each half.
    from src.infrastructure.rest.contracts.documents import DocumentSummary
    from src.infrastructure.rest.contracts.entities import EntitySummary

    for model in (DocumentSummary, EntitySummary):
        assert issubclass(model, BaseModel)
        assert model.model_config.get("extra") == "forbid", model
        assert model.model_json_schema()["additionalProperties"] is False, model

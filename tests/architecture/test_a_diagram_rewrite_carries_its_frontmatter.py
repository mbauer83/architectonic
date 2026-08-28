"""Every call that rewrites an existing diagram hands back the frontmatter it is not changing.

**`format_diagram_puml` writes only what it is given, so a field omitted is a field deleted.** That
makes every call site a place where a diagram can lose data silently, and one of the four did: the
project cascade delete passed eleven arguments of twenty and stripped `keywords`,
`authored-groupings`, `bindings`, `edge-labels`, `viewpoint`, `view_derivations`,
`diagram-format-version`, `manual-layout` — which is what stops a hand-laid body being regenerated —
and `tlp`, a confidentiality classification. Nothing failed: the operation reported `applied: true`,
the file verified, and the fields were simply gone.

A register rather than a fourth bespoke test, for the reason the syntax register exists: the defect is
not "this site is wrong", it is "there is no place where a new site has to declare which kind it is".

**Two kinds, and the distinction is what makes omission safe or unsafe.**

* A **rewrite** reads an existing file and writes it back. It must pass `carried_diagram_fields`,
  because anything it omits is deleted from a file that had it.
* A **create** writes a file that did not exist. Omission loses nothing *provided the function cannot
  be told the field in the first place* — so the rule for a create site is that it must not accept a
  carried field it then drops. That is the half that would otherwise let "it's a create" excuse a real
  loss, and it is checked, not asserted.
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.application.modeling.artifact_write_formatting import (
    CarriedDiagramFields,
    format_diagram_puml,
)
from tests.support.source_paths import REPO_ROOT

#: The arguments a rewrite must hand back. Read from the TypedDict rather than listed again here, so
#: a field added to the carry-over set is covered by this gate without editing it.
CARRIED = frozenset(CarriedDiagramFields.__annotations__)

#: Everything the formatter can be told.
EVERY_FIELD = frozenset(inspect.signature(format_diagram_puml).parameters)


@dataclass(frozen=True)
class FormatterCallSite:
    """One place `format_diagram_puml` is called, and which kind of write it performs."""

    module: Path
    #: The enclosing function, so a move is a visible edit here rather than a silent re-file.
    function: str
    #: "rewrite" — reads a file and writes it back. "create" — writes a file that did not exist.
    kind: str
    #: Why it is that kind, in the words a reviewer would check it by.
    because: str


CALL_SITES: tuple[FormatterCallSite, ...] = (
    FormatterCallSite(
        module=Path("src/infrastructure/write/artifact_write/diagram_edit.py"),
        function="edit_diagram",
        kind="rewrite",
        because="edits a stored diagram; every field is resolved from the argument or the stored value",
    ),
    FormatterCallSite(
        module=Path("src/infrastructure/write/artifact_write/cascade_delete.py"),
        function="_rewrite_foreign_diagram",
        kind="rewrite",
        because=(
            "rewrites a foreign diagram after a project cascade delete. This is the site that lost "
            "nine fields, `tlp` and `manual-layout` among them"
        ),
    ),
    FormatterCallSite(
        module=Path("src/infrastructure/write/artifact_write/diagram.py"),
        function="create_diagram",
        kind="create",
        because="creates a new diagram; there is no stored value to carry",
    ),
    FormatterCallSite(
        module=Path("src/infrastructure/write/artifact_write/admin_diagram_ops.py"),
        function="_write_diagram_to_enterprise",
        kind="create",
        because=(
            "writes a diagram into the enterprise catalogue under a freshly allocated id, so the "
            "path is always new"
        ),
    ),
)


def _calls_in(module: Path) -> list[tuple[str, ast.Call]]:
    """Every `format_diagram_puml(...)` call in *module*, with the function that encloses it."""
    tree = ast.parse((REPO_ROOT / module).read_text(encoding="utf-8"))
    found: list[tuple[str, ast.Call]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == "format_diagram_puml"
            ):
                found.append((node.name, inner))
    return found


def _named_arguments(call: ast.Call) -> set[str]:
    return {keyword.arg for keyword in call.keywords if keyword.arg is not None}


def _unpacks_the_carry_over(call: ast.Call) -> bool:
    """Does this call spread `carried_diagram_fields(...)` into itself?"""
    return any(
        keyword.arg is None
        and isinstance(keyword.value, ast.Call)
        and isinstance(keyword.value.func, ast.Name)
        and keyword.value.func.id == "carried_diagram_fields"
        for keyword in call.keywords
    )


def test_every_call_site_has_a_row() -> None:
    """A new call site is a new place a diagram can lose data, so it declares which kind it is."""
    registered = {(site.module, site.function) for site in CALL_SITES}
    found: set[tuple[Path, str]] = set()
    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        module = path.relative_to(REPO_ROOT)
        if "format_diagram_puml(" not in path.read_text(encoding="utf-8"):
            continue
        for function, _call in _calls_in(module):
            found.add((module, function))

    assert found == registered, (
        "the register and the code disagree.\n"
        f"  unregistered call sites: {sorted(found - registered)}\n"
        f"  rows with no call site : {sorted(registered - found)}\n"
        "Add a row saying whether the site rewrites an existing diagram or creates a new one."
    )


@pytest.mark.parametrize(
    "site", [s for s in CALL_SITES if s.kind == "rewrite"], ids=lambda s: s.function
)
def test_a_rewrite_hands_back_what_it_is_not_changing(site: FormatterCallSite) -> None:
    calls = [call for function, call in _calls_in(site.module) if function == site.function]
    assert calls, f"{site.function} no longer calls the formatter"
    for call in calls:
        named = _named_arguments(call)
        missing = CARRIED - named
        assert not missing or _unpacks_the_carry_over(call), (
            f"{site.module}:{site.function} rewrites a stored diagram ({site.because}) and omits "
            f"{sorted(missing)}. The formatter writes only what it is given, so each of those is "
            f"deleted from a file that had it. Pass `**carried_diagram_fields(frontmatter)`."
        )


@pytest.mark.parametrize(
    "site", [s for s in CALL_SITES if s.kind == "create"], ids=lambda s: s.function
)
def test_a_create_cannot_be_told_a_field_it_then_drops(site: FormatterCallSite) -> None:
    """The half that stops "it's a create" excusing a real loss.

    A create may omit a carried field, because no stored file had it. It may *not* accept that field
    from its own caller and then not pass it on — that is the same silent loss wearing a different
    hat.
    """
    module_ast = ast.parse((REPO_ROOT / site.module).read_text(encoding="utf-8"))
    enclosing = next(
        node for node in ast.walk(module_ast)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == site.function
    )
    accepted = {
        argument.arg
        for argument in [*enclosing.args.args, *enclosing.args.kwonlyargs]
    }
    calls = [call for function, call in _calls_in(site.module) if function == site.function]
    assert calls, f"{site.function} no longer calls the formatter"
    for call in calls:
        passed = _named_arguments(call)
        accepted_but_dropped = (accepted & CARRIED) - passed
        assert not accepted_but_dropped or _unpacks_the_carry_over(call), (
            f"{site.module}:{site.function} is registered as a create ({site.because}) but takes "
            f"{sorted(accepted_but_dropped)} from its caller and does not pass it on, so the caller's "
            f"value is silently discarded."
        )


def test_the_carry_over_set_is_every_field_a_stored_diagram_can_hold() -> None:
    """The carry-over set is defined against the formatter, not maintained beside it.

    What is deliberately *not* carried: the identity and status a rewrite always restates for itself,
    the body, and the two reference lists a rewrite recomputes. Anything else the formatter can write
    is a field a stored diagram may hold, so it has to be carried or this gate is incomplete.
    """
    restated_by_every_rewrite = {
        "artifact_id", "diagram_type", "name", "version", "status", "last_updated", "puml_body",
        "entity_ids_used", "connection_ids_used", "diagram_entities", "diagram_connections",
    }

    uncovered = EVERY_FIELD - CARRIED - restated_by_every_rewrite

    assert not uncovered, (
        f"{sorted(uncovered)} can be written to a diagram's frontmatter and is neither carried "
        f"across a rewrite nor restated by one, so a rewrite silently deletes it. Add it to "
        f"`CarriedDiagramFields` and `carried_diagram_fields`."
    )

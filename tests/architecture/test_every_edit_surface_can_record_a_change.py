"""Every surface that edits an artifact can record a change against an enterprise-owned one.

Editing content this repository does not own writes nothing: it records a change against the
promoted artifact, and recording one means reading what is already pending — which is what the
`repo` argument is for. A surface that omits it does not fail. It returns a refusal saying "this
caller supplied no repository to record it in", which reads like a deliberate policy and is in fact
a caller that forgot.

**That is not hypothetical: it was every surface.** The write path was finished, tested and
committed, and not one MCP tool or REST route passed a repository — so the feature was unreachable
from outside the test suite, and nothing said so. A fitness function is the only thing that can
notice, because each call site is correct on its own terms.

Read out of the source rather than by calling the surfaces: the question is whether the argument is
*passed*, and a runtime test would need a promoted artifact, both tiers and a live index to ask a
question that is answerable by looking.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

#: The write functions that record a change rather than writing, when the artifact is not ours.
_RECORDING_EDITS = frozenset({"edit_entity", "edit_document", "edit_diagram"})

#: Call sites that legitimately pass no repository, each with the reason it cannot.
#:
#: The bulk apply writes into a *staged* workspace and commits it as one transaction; a change
#: recorded there would be read back from the staged repository rather than the served one, which is
#: its own decision and not this one. The exchange adapter imports a foreign model and has no
#: repository to hand. Both refuse with the explanatory message rather than corrupting anything,
#: which is the safe half of the behaviour — they simply do not offer the feature.
_WITHOUT_A_REPOSITORY: dict[str, str] = {
    "src/infrastructure/mcp/artifact_mcp/bulk/write_apply.py": "writes into a staged workspace",
    "src/infrastructure/exchange/archimate_model_exchange/write_adapter.py": "imports a foreign model",
    "src/infrastructure/mcp/artifact_mcp/_diagram_binding_modes.py": (
        "resolves the diagram's own file before editing, so a reference never reaches the edit"
    ),
}

_SURFACES = ("src/infrastructure/mcp", "src/infrastructure/rest", "src/infrastructure/exchange")


#: How REST performs a write: the edit function is *handed* to the policy wrapper with the arguments
#: beside it, rather than called. Reading only direct calls found none of them — this file's first
#: version passed while every REST route was missing its repository, which is why the rule is that a
#: new gate is neutered and re-run before it is believed.
_POLICY_WRAPPER = "authorized_write"


def _callee(node: ast.Call, aliases: dict[str, str]) -> str | None:
    match node.func:
        case ast.Attribute(attr=attr):
            return aliases.get(attr, attr)
        case ast.Name(id=name):
            return aliases.get(name, name)
        case _:
            return None


def _handed_off(node: ast.Call, aliases: dict[str, str]) -> str | None:
    """The edit function this policy-wrapped call performs, if it is one."""
    if _callee(node, aliases) != _POLICY_WRAPPER:
        return None
    return next(
        (
            resolved
            for argument in node.args
            if isinstance(argument, ast.Name)
            and (resolved := aliases.get(argument.id, argument.id)) in _RECORDING_EDITS
        ),
        None,
    )


def _aliases(tree: ast.Module) -> dict[str, str]:
    """Local names back to what they were imported as — REST imports `edit_entity as _edit`."""
    return {
        alias.asname or alias.name: alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }


def _call_sites(repo_root: Path) -> list[tuple[str, str, bool]]:
    """Every call performing a recording edit under a surface: (path, function, passes a repository)."""
    found: list[tuple[str, str, bool]] = []
    for surface in _SURFACES:
        for path in sorted((repo_root / surface).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            aliases = _aliases(tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                direct = _callee(node, aliases)
                performed = direct if direct in _RECORDING_EDITS else _handed_off(node, aliases)
                if performed is not None:
                    found.append((
                        path.relative_to(repo_root).as_posix(),
                        performed,
                        any(keyword.arg == "repo" for keyword in node.keywords),
                    ))
    return found


@pytest.fixture(scope="module")
def call_sites() -> list[tuple[str, str, bool]]:
    return _call_sites(Path(__file__).resolve().parents[2])


def test_the_edit_surfaces_are_still_where_this_expects(call_sites) -> None:  # noqa: ANN001
    """A guard that reads nothing is a guard that passes. If the surfaces move, this must be told."""
    assert call_sites, "no edit call sites found under the MCP or REST surfaces"


def test_every_edit_surface_passes_a_repository(call_sites) -> None:  # noqa: ANN001
    missing = [
        (path, function)
        for path, function, passes in call_sites
        if not passes and path not in _WITHOUT_A_REPOSITORY
    ]
    assert not missing, (
        "these surfaces edit an artifact without supplying a repository, so an edit of "
        "enterprise-owned content is refused instead of recorded:\n"
        + "\n".join(f"  {path}: {function}" for path, function in missing)
        + "\nPass `repo=`, or name the call site in `_WITHOUT_A_REPOSITORY` with the reason it cannot."
    )


def test_the_exemptions_are_all_still_real(call_sites) -> None:
    """A shrink-only list: an exemption that no longer names a call site is one nobody removed."""
    edited = {path for path, _function, _passes in call_sites}
    stale = sorted(set(_WITHOUT_A_REPOSITORY) - edited)
    assert not stale, f"exempted call sites that no longer edit anything: {stale}"

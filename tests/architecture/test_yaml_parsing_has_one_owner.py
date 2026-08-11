"""One module decides how this project parses YAML, and nothing else calls a loader directly.

`yaml.safe_load` was written out at 77 call sites, each independently choosing the **pure-Python**
loader on a machine where `libyaml` is present. A verification pass over 880 files parses ~200,000 YAML
documents, and a profile put the pass's time in `yaml/scanner.py`; on this repository's own corpus the C
loader is 9.5x faster for identical results.

The fix was worth nothing if it can erode. A new module written next month will reach for
`yaml.safe_load` — it is the obvious call, it is in every tutorial, and it will silently reintroduce the
pure-Python loader for whatever it parses. So the single owner is asserted here rather than trusted:

* nothing outside `domain/yaml_documents.py` names a PyYAML load function, and
* nothing outside it names a loader class.

Serialisation is deliberately out of scope. `yaml.safe_dump` has an equivalent C dumper, but no profile
blames it here, so it keeps its own call sites rather than being centralised on speculation — and a test
that claimed to own "YAML" while covering only half of it would be worse than this one.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

from tests.support.source_paths import REPO_ROOT, SRC, TOOLS

#: The module that owns the choice. Relative to the repository root, so a move is a visible edit here.
_OWNER = Path("src/domain/yaml_documents.py")

#: PyYAML's parse entry points. `load` is included because passing a loader explicitly is exactly the
#: decision this module exists to make once.
_LOAD_FUNCTIONS = frozenset({"safe_load", "safe_load_all", "load", "load_all", "full_load", "unsafe_load"})

#: Naming a loader class is the same decision by another route.
_LOADER_CLASSES = frozenset({"SafeLoader", "CSafeLoader", "Loader", "CLoader", "FullLoader", "UnsafeLoader"})


#: Directories that hold vendored or generated code, not code this repository authors.
_NOT_OURS = frozenset({"node_modules", "__pycache__", ".venv"})


def _python_files() -> list[Path]:
    return sorted(
        path
        for root in (SRC, TOOLS)
        for path in root.rglob("*.py")
        if _NOT_OURS.isdisjoint(path.parts)
    )


def _yaml_names_used(path: Path) -> list[str]:
    """Every PyYAML name this file reaches for, however it reached: attribute access or from-import."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    aliases = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name == "yaml"
    }
    attributes = [
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in aliases
    ]
    # `from yaml import CSafeLoader` is the same decision without an attribute access.
    imported = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "yaml"
        for alias in node.names
    ]
    return attributes + imported


def _files_naming_any_of(names: Iterable[str]) -> dict[str, list[str]]:
    """Which files outside the owner reach for one of `names`, and which ones they reached for."""
    wanted = frozenset(names)
    return {
        str(path.relative_to(REPO_ROOT)): sorted(found)
        for path in _python_files()
        if path.relative_to(REPO_ROOT) != _OWNER and (found := wanted.intersection(_yaml_names_used(path)))
    }


def test_the_owner_module_exists_where_this_test_expects_it() -> None:
    # Without this, moving or deleting the module would make every assertion below vacuously true.
    assert (REPO_ROOT / _OWNER).is_file(), f"{_OWNER} is the single owner and it is not there"


def test_only_the_owner_calls_a_yaml_load_function() -> None:
    offenders = _files_naming_any_of(_LOAD_FUNCTIONS)

    assert offenders == {}, (
        "these call a PyYAML loader directly, which re-decides — and on this machine loses — the "
        "loader choice `src/domain/yaml_documents.parse_yaml` makes once. Call `parse_yaml` instead: "
        f"{offenders}"
    )


def test_only_the_owner_names_a_loader_class() -> None:
    offenders = _files_naming_any_of(_LOADER_CLASSES)

    assert offenders == {}, (
        "naming a loader class is the same choice by another route; it belongs in "
        f"`src/domain/yaml_documents.py`: {offenders}"
    )


def test_the_scan_sees_the_files_it_means_to() -> None:
    """A walk that found nothing would report a compliant repository.

    Anchored on the owner being found and on a known parser being in range, so an rglob that stopped
    working fails here rather than passing the two assertions above.
    """
    files = _python_files()
    assert len(files) > 500, len(files)
    relative = {str(p.relative_to(REPO_ROOT)) for p in files}
    assert str(_OWNER) in relative
    assert "src/domain/repository/connection_declaration.py" in relative

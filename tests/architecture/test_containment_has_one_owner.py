"""Whether one location lies inside another is answered by `repository_confinement`, and nowhere else.

`Path.is_relative_to` compares spellings: a relative root, a `..` or a symlinked repository gives a
different answer from the confinement owner, which resolves both sides before comparing. Nine call
sites asked the raw question after the owner existed — one of them resolving the path and not the
mount root it compared against, so a repository reached through a link belonged to no mount.

A caller asks `is_within` (or, where it needs the location inside, `canonical` on both sides).
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.support.source_paths import REPO_ROOT, SRC, TOOLS, python_sources

_OWNER = Path("src/application/repository_confinement.py")


def _raw_containment_calls(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "is_relative_to"
    )


def test_the_owner_is_where_this_rule_says() -> None:
    assert (REPO_ROOT / _OWNER).is_file()
    assert _raw_containment_calls(REPO_ROOT / _OWNER), "the owner no longer answers the question itself"


def test_nothing_outside_the_owner_asks_whether_a_path_is_inside_another() -> None:
    offenders = {
        str(relative): lines
        for path in python_sources(SRC, TOOLS)
        if (relative := path.relative_to(REPO_ROOT)) != _OWNER
        and (lines := _raw_containment_calls(path))
    }
    assert not offenders, (
        "Ask `repository_confinement.is_within` instead of `Path.is_relative_to`, which compares "
        f"spellings rather than locations: {offenders}"
    )


def test_the_detector_sees_a_raw_comparison(tmp_path: Path) -> None:
    source = tmp_path / "reader.py"
    source.write_text("def inside(p, r):\n    return p.is_relative_to(r)\n", encoding="utf-8")

    assert _raw_containment_calls(source) == [2]

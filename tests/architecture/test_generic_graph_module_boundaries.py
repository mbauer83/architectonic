"""Generic graph modules must not know any module's vocabulary.

`GraphCanvas` states the contract in its own header: "Domain-agnostic by contract — it
receives normalized nodes/edges plus presentation callbacks … it never imports architecture,
assurance, or viewpoint concepts." The canvas, its layout helpers and its interaction
composables serve every graph surface in the product, and modules plug into that core rather
than the core enumerating them.

A contract stated only in prose is a contract that erodes. The pull is always the same and
always local: the ordering rule is needed *here*, the domain names are right *there*, and a
table of them is three lines. The result compiles, passes every test, and quietly makes the
shared core unusable by the next module — whose vocabulary it does not contain.

Comments are stripped and the rest is matched whole-word, so naming a domain in prose to
explain a caller stays legal while `'motivation'` — or the unquoted object key `motivation:`,
which is how the vocabulary actually arrived here — does not. Matching quoted literals alone
would have missed it: a placement table keys on bare identifiers.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GUI_SRC = REPO_ROOT / "tools" / "gui" / "src"

#: Modules whose whole purpose is to be reusable across surfaces. Graph rendering came first;
#: the list has since grown to the shared browse and navigation components, which are held to the
#: same standard for the same reason — `NavTree` files entities under a framework group on the
#: architecture side and nodes under an analysis on the assurance side, and a component that knew
#: either vocabulary would be wrong for the other one first.
_GENERIC_GRAPH_MODULES = (
    "ui/components/GraphCanvas.vue",
    "ui/components/GraphCanvas.helpers.ts",
    "ui/composables/useForceGraph.ts",
    "ui/composables/useForceGraphLayout.ts",
    "ui/composables/forceSimulation.ts",
    "ui/composables/useGraphPanZoom.ts",
    "ui/composables/useElementSize.ts",
    "ui/components/NavTree.vue",
    "ui/components/GroupedRowTree.vue",
    "ui/components/FilterBar.vue",
)


def _ontology_domain_names() -> frozenset[str]:
    """The domains the ontology declares — read, never restated."""
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry

    names = build_runtime_catalogs(get_module_registry()).ontology.known_domain_names()
    # "common" and "unknown" are generic English and carry no module meaning on their own.
    return frozenset(str(name) for name in names) - {"common", "unknown"}


def _module_vocabulary() -> frozenset[str]:
    """Every word one module owns: the ontology's domains, plus the assurance method names.

    The assurance half matters because these components are now shared *between* the two areas.
    `NavTree` files entities under a framework group for the architecture browse surface and nodes
    under an analysis for the assurance nav; a branch on `STPA` there would make it unusable for
    the first, exactly as a branch on `motivation` makes it unusable for the second.
    """
    from src.domain.assurance.assurance_analysis import ANALYSIS_METHODS

    return _ontology_domain_names() | frozenset(ANALYSIS_METHODS)


_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"//[^\n]*")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)


def _code_without_comments(source: str) -> str:
    """Prose explaining a caller is fine; only executable code couples to a vocabulary."""
    for pattern in (_BLOCK_COMMENT, _LINE_COMMENT, _HTML_COMMENT):
        source = pattern.sub(" ", source)
    return source


def _identifiers(source: str) -> set[str]:
    """Whole-word tokens, so both `'motivation'` and the bare key `motivation:` are seen."""
    return set(re.findall(r"[A-Za-z][A-Za-z0-9_-]*", _code_without_comments(source)))


@pytest.mark.parametrize("relative_path", _GENERIC_GRAPH_MODULES)
def test_no_module_vocabulary_in_a_generic_graph_module(relative_path: str) -> None:
    path = GUI_SRC / relative_path
    assert path.is_file(), f"{relative_path} no longer exists; update the boundary list"

    leaked = sorted(_identifiers(path.read_text(encoding="utf-8")) & _module_vocabulary())

    assert leaked == [], (
        f"{relative_path} branches on module vocabulary {leaked}. This module is shared across "
        "surfaces, so a vocabulary baked in here is one the next module cannot use. "
        "Take the mapping as a parameter and let the caller that owns the vocabulary supply it."
    )


def test_the_boundary_list_still_describes_real_modules() -> None:
    """A renamed module must not silently drop out of the policy."""
    missing = [path for path in _GENERIC_GRAPH_MODULES if not (GUI_SRC / path).is_file()]

    assert missing == [], f"boundary list names modules that no longer exist: {missing}"

"""A cached verdict is discarded when anything it was computed from changes.

The incremental verifier reuses a file's stored result while neither the file nor the verifier has
changed, and "the verifier" is what `verifier_engine_signature` hashes. It hashed the verification
package alone. That package dispatches rules; it decides few of them. The domain says what a
relationship may join, a diagram type what its own statements mean, an ontology's YAML which types
exist, and the reader of a rendered picture is not even imported — the composition root hands it in.
A rule corrected in any of those went on being served from the cache as it stood before.

The signature now covers the whole product source, so nothing is listed. This test is what keeps it
that way: it walks what the verifier actually reaches — by import from the rule modules and from
its composition root, and by registration for diagram types and ontology data — and fails if any of
it lies outside what is hashed. It is also run against the coverage as it used to be, and must find
the gap, so a walk that silently found nothing cannot pass.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterable
from pathlib import Path

from src.application.verification.artifact_verifier_incremental import PRODUCT_SOURCE, engine_source_files
from tests.support.source_paths import REPO_ROOT

#: Where a verdict's code starts: the rules, and the composition root that wires in the adapters a
#: rule is handed rather than imports.
_ROOTS = (
    PRODUCT_SOURCE / "application" / "verification",
    PRODUCT_SOURCE / "infrastructure" / "verification",
)

#: Packages a verdict reaches without any import showing it: diagram types contribute rules by
#: registration, and ontologies are loaded as data.
_REACHED_BY_REGISTRATION = (PRODUCT_SOURCE / "diagram_types", PRODUCT_SOURCE / "ontologies")


def _module_file(dotted: str) -> Path | None:
    """The file in this repository a dotted name resolves to, or None for the standard library and
    third parties. Not limited to `src`: a rule importing from beside it is exactly what to find."""
    base = REPO_ROOT.joinpath(*dotted.split("."))
    if base.with_suffix(".py").is_file():
        return base.with_suffix(".py")
    return base / "__init__.py" if (base / "__init__.py").is_file() else None


def _imports_of(path: Path) -> Iterable[Path]:
    """Every first-party file *path* imports, wherever in the module the import stands."""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            # `from package import module` names a module as often as it names a value.
            names = [node.module, *(f"{node.module}.{alias.name}" for alias in node.names)]
        else:
            continue
        yield from (found for name in names if (found := _module_file(name)) is not None)


def _reached_by_import() -> set[Path]:
    reached: set[Path] = set()
    pending = [path for root in _ROOTS for path in root.glob("*.py")]
    while pending:
        path = pending.pop()
        if path in reached:
            continue
        reached.add(path)
        pending.extend(_imports_of(path))
    return reached


def _everything_a_verdict_reaches() -> set[Path]:
    registered = {
        path
        for package in _REACHED_BY_REGISTRATION
        for path in package.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    return _reached_by_import() | registered


def _unhashed(covered: Callable[[Path], bool]) -> list[str]:
    return sorted(
        str(path.relative_to(REPO_ROOT)) for path in _everything_a_verdict_reaches() if not covered(path)
    )


def test_everything_a_verdict_is_computed_from_is_hashed() -> None:
    hashed = set(engine_source_files(PRODUCT_SOURCE))

    unhashed = _unhashed(hashed.__contains__)

    assert unhashed == [], (
        "the verifier reaches these and the engine signature does not hash them, so a change to "
        f"one leaves every cached verdict standing: {unhashed}"
    )


def test_the_walk_reaches_what_a_rule_is_decided_in() -> None:
    """The walk is the instrument; if it stopped following imports the test above would pass on
    an empty set. These are a rule's domain logic, an adapter handed in at composition, a diagram
    type's own contribution and an ontology's data — one of each way a verdict is reached."""
    reached = {path.relative_to(PRODUCT_SOURCE).as_posix() for path in _everything_a_verdict_reaches()}

    assert "domain/diagrams/layout/picture_checks.py" in reached
    assert "infrastructure/rendering/layout/plantuml_svg_reader.py" in reached
    assert "domain/relationships/relationship_mediation.py" in reached
    assert any(path.startswith("diagram_types/activity/") for path in reached)
    assert any(path.startswith("ontologies/") and path.endswith(".yaml") for path in reached)


def test_the_coverage_this_replaced_is_found_wanting() -> None:
    """The verification package alone, as the signature used to hash: the gap this test exists for
    must be visible to it — in what already existed, and in the picture checks that exposed it."""
    verification_package = _ROOTS[0]

    unhashed = _unhashed(lambda path: path.parent == verification_package)

    assert "src/domain/diagrams/layout/picture_checks.py" in unhashed
    assert "src/infrastructure/rendering/layout/plantuml_svg_reader.py" in unhashed
    assert "src/domain/relationships/relationship_mediation.py" in unhashed
    assert any(path.startswith("src/diagram_types/") for path in unhashed)

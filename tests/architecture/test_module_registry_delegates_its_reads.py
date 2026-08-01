"""The registry registers; the catalog answers. One implementation of the merge rules.

``ModuleRegistry`` is the mutable authority over what is registered and ``ModuleCatalog`` is the
frozen snapshot the composition root hands consumers. Both need the same twenty-one queries, and both
had them: twelve method bodies byte-identical, the rest differing only in whether the aggregation was
memoised or copied. Nothing held the pair equal, so "what the registry answers" and "what the catalog
answers" were two questions — over the same modules, with the same merge rules written twice.

The rules are the catalog's now and the registry delegates. This test keeps it that way, structurally
rather than by comparing answers: a re-implemented method that happens to agree today is the state
this file exists to prevent.
"""

from __future__ import annotations

import ast

from src.domain.modules.module_catalog import ModuleCatalog
from src.domain.modules.module_registry import ModuleRegistry
from tests.support.source_paths import SRC

_MODULES = SRC / "domain" / "modules"

#: Registry members that are not queries: registration, and the snapshot the queries go through.
_NOT_A_QUERY = frozenset({
    "__init__", "catalog", "_registrations_changed",
    "register_ontology", "unregister_ontology", "replace_ontology",
    "register_diagram_type", "unregister_diagram_type", "replace_diagram_type",
})


def _methods(module: str, class_name: str) -> dict[str, ast.FunctionDef]:
    tree = ast.parse((_MODULES / module).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                member.name: member
                for member in node.body
                if isinstance(member, ast.FunctionDef)
            }
    raise AssertionError(f"{class_name} not found in {module}")


def _delegates_to_catalog(method: ast.FunctionDef) -> bool:
    """Whether the body is exactly ``return self.catalog.<same name>(…)`` and nothing else."""
    if len(method.body) != 1:
        return False
    statement = method.body[0]
    if not isinstance(statement, ast.Return) or not isinstance(statement.value, ast.Call):
        return False
    called = statement.value.func
    return (
        isinstance(called, ast.Attribute)
        and called.attr == method.name
        and isinstance(called.value, ast.Attribute)
        and called.value.attr == "catalog"
        and isinstance(called.value.value, ast.Name)
        and called.value.value.id == "self"
    )


def test_every_registry_query_delegates_to_the_catalog() -> None:
    registry = _methods("module_registry.py", "ModuleRegistry")
    offenders = sorted(
        name
        for name, method in registry.items()
        if name not in _NOT_A_QUERY and not _delegates_to_catalog(method)
    )
    assert offenders == [], (
        "These ModuleRegistry methods answer a query themselves instead of delegating to "
        "`self.catalog`. The merge rules — which module wins a duplicated type, whether diagram-type "
        f"connection types join the ontologies' — belong in one place: {offenders}"
    )


def test_the_registry_delegates_the_whole_read_surface() -> None:
    # The other direction: a catalog query the registry does not expose would send a caller back to
    # building its own snapshot from `_ontologies`, which is where the second copy came from.
    catalog_queries = {
        name for name in _methods("module_catalog.py", "ModuleCatalog") if not name.startswith("_")
    }
    registry_queries = set(_methods("module_registry.py", "ModuleRegistry")) - _NOT_A_QUERY
    missing = sorted(catalog_queries - registry_queries)
    assert missing == [], f"ModuleCatalog answers these and ModuleRegistry does not: {missing}"


def test_the_snapshot_follows_a_registration() -> None:
    # Delegation through a memoised snapshot is only correct while the snapshot is dropped on
    # change: a registry answering from before a hot-reload is worse than one that recomputes.
    registry = ModuleRegistry()
    assert registry.all_ontologies() == {}
    first = registry.catalog

    from src.ontologies import archimate_4

    registry.register_ontology(archimate_4.module)
    assert registry.catalog is not first
    assert archimate_4.module.name in registry.all_ontologies()
    assert registry.all_entity_types() != {}

    registry.unregister_ontology(archimate_4.module.name)
    assert registry.all_ontologies() == {}
    assert registry.all_entity_types() == {}


def test_the_scanner_reads_the_delegation_it_is_looking_for() -> None:
    delegating = ast.parse("def f(self):\n    return self.catalog.f()\n").body[0]
    assert isinstance(delegating, ast.FunctionDef)
    assert _delegates_to_catalog(delegating)

    reimplemented = ast.parse("def f(self):\n    return {}\n").body[0]
    assert isinstance(reimplemented, ast.FunctionDef)
    assert not _delegates_to_catalog(reimplemented)

    # A method delegating to the *wrong* catalog query is not delegation either.
    misrouted = ast.parse("def f(self):\n    return self.catalog.g()\n").body[0]
    assert isinstance(misrouted, ast.FunctionDef)
    assert not _delegates_to_catalog(misrouted)

    assert len(_methods("module_registry.py", "ModuleRegistry")) > 20
    assert issubclass(ModuleCatalog, object)

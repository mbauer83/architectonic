"""A diagram-type module does not spell the ontology's own serialised forms itself.

Two shapes were copied into every module that needed them, and both copies were invisible:

* the permitted-mapping source, ``{ontology, entity_type, entity_class, transparent}`` — written out
  at five call sites, four modules and the write boundary's guidance serialiser, while
  ``mapping_spec_from_config`` owned the *reading* of the same four keys in one place;
* the ontology→config fold for a module's own constructs — four copies, near-identical, differing
  only where one had drifted: ``c4`` dropped ``required_connections``, three modules dropped
  ``identity_scope`` and ``id_prefix``.

None of the drift showed. The parsed config supplies the same defaults the omissions happened to
need, so every affected construct looked right; a module adding a construct with a non-default
identity scope would have had it published or dropped depending on which copy it inherited.

Both now have one home: :meth:`PermittedMappingSpec.as_config` and
:func:`merge_ontology_into_diagram_only_types`. This test is what keeps them single, keyed on the
*literal keys* rather than on a function name — the copies were not calls to anything, which is why
nothing caught them.
"""

from __future__ import annotations

import ast
from pathlib import Path

from src.domain.ontology_representation.ontology_types import (
    MappingSourceSpec,
    PermittedMappingSpec,
    mapping_spec_from_config,
)
from tests.support.source_paths import REPO_ROOT, SRC

_DIAGRAM_TYPES = SRC / "diagram_types"

#: The module that owns each serialised form, and may therefore spell it.
_OWNERS = {
    "src/domain/ontology_representation/ontology_types.py",
    "src/domain/diagrams/diagram_ontology_merge.py",
}

#: The four keys a permitted-mapping source is. A dict literal carrying all of them is a copy of the
#: projection, whatever it is called.
_SOURCE_KEYS = frozenset({"ontology", "entity_type", "entity_class", "transparent"})


def _python_sources() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _dict_literal_key_sets(tree: ast.AST) -> list[frozenset[str]]:
    return [
        frozenset(
            key.value
            for key in node.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        )
        for node in ast.walk(tree)
        if isinstance(node, ast.Dict)
    ]


def test_the_permitted_mapping_source_is_spelled_in_exactly_one_place() -> None:
    offenders = []
    for path in _python_sources():
        relative = path.relative_to(REPO_ROOT).as_posix()
        if relative in _OWNERS:
            continue
        for keys in _dict_literal_key_sets(ast.parse(path.read_text(encoding="utf-8"))):
            if _SOURCE_KEYS <= keys:
                offenders.append(relative)
                break
    assert offenders == [], (
        "These modules build a permitted-mapping source by hand. Use "
        "`PermittedMappingSpec.as_config()`, whose round trip with `mapping_spec_from_config` is "
        f"the single statement of that form: {offenders}"
    )


def test_no_module_folds_the_ontology_into_its_own_config() -> None:
    # Keyed on the field set the fold writes, for the same reason: the four copies were private
    # functions with four different names in four packages.
    folded = {"classes", "create_when", "never_create_when", "mapping_required"}
    offenders = []
    for path in sorted(_DIAGRAM_TYPES.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        assignments = {
            node.slice.value
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        }
        if folded <= assignments:
            offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == [], (
        "These modules copy the ontology's statement about an own construct into their config "
        "themselves. Call `merge_ontology_into_diagram_only_types`, which emits every field the "
        f"config parser reads rather than the subset one module happened to need: {offenders}"
    )


def test_the_scanner_reads_the_shapes_it_is_looking_for() -> None:
    # Without these, an AST walk that stopped matching would report no offenders over an empty scan.
    assert len(_python_sources()) > 300
    owner = ast.parse((SRC / "domain/ontology_representation/ontology_types.py").read_text())
    assert any(_SOURCE_KEYS <= keys for keys in _dict_literal_key_sets(owner))
    assert _dict_literal_key_sets(ast.parse("d = {'ontology': 1}")) == [frozenset({"ontology"})]


def test_every_owner_named_here_exists() -> None:
    # A stale owner would excuse whatever is later written at that path.
    for relative in sorted(_OWNERS):
        assert (REPO_ROOT / relative).is_file(), relative


def test_the_projection_and_the_parser_still_agree() -> None:
    # The property the single home rests on, asserted here too: this file's whole claim is that one
    # place is enough, which is only true while that place round-trips.
    spec = PermittedMappingSpec(
        entity_types=("role",),
        sources=(MappingSourceSpec(ontology="archimate_4", entity_class="behavior-element"),),
    )
    assert mapping_spec_from_config(spec.as_config()) == spec

"""The plug-in core must not know one module's words.

`src/domain/` is two things wearing one name. `ontology_representation/` and `modules/` are the
core that modules register *with*: capability Protocols, catalogs, the record shapes every module
shares. `src/domain/assurance/`, `src/domain/repository/` and their siblings are one module's own
domain. "It is a domain concept" therefore says nothing about where it belongs — the question is
whose vocabulary it is.

An import check cannot catch this. The violation that prompted this test added no import: a
property named `analysis_methods`, returning STPA/CAST/GRC/FMEA, on the generic
`StoreGraphProjectingDiagramType` capability. That capability says only "this type draws from a
live graph rather than a file", which any module with a store behind it can satisfy; naming one
module's methods on it excludes every other. Nothing failed, because nothing else had a store yet.

So the check is lexical, over the vocabulary the assurance module owns. What it protects is the
substitutability of the capability protocols: a second store-backed module must be able to
implement them without inheriting assurance's concepts.

**Scope, stated rather than implied.** This covers the assurance vocabulary only. The core also
carries ArchiMate terms — `archimate_relationship_type` on `ConnectionTypeInfo`,
`archimate_stereotype_to_connection_type` on the catalog — which predate this test by a long way
and are a real, separate boundary debt: an ontology-specific field sitting on a shared record. They
are not silently excluded here; they are simply not what this test claims to hold, and adding them
would turn it into a baseline table nobody reads. Extend the vocabulary below when a module gains
words of its own.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.domain.assurance.assurance_analysis import ANALYSIS_METHODS

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: Packages under `src/domain/` that are the plug-in core rather than one module's domain.
_CORE_PACKAGES = (
    "src/domain/ontology_representation",
    "src/domain/modules",
)

#: The assurance module's own packages. Held to the mirror rule: they must not hard-code another
#: module's vocabulary either. The leak this caught was `FMEA_DOMAINS = {"application", "business",
#: "technology", "common"}` and `ACTING_CLASSES = {"active-structure-element", "behavior-element"}`
#: in `src/domain/assurance/fmea_analysable_elements.py` — ArchiMate's words, sitting in assurance,
#: to decide which elements an FMEA is about. The ontology now declares which of its types act and
#: assurance asks; that module is gone.
_ASSURANCE_PACKAGES = (
    "src/domain/assurance",
)

#: Words belonging to the assurance module. The analysis methods come from the module's own
#: vocabulary constant, so a new method is covered without editing this list; the rest are the
#: method names' close relatives — a type name is as much a leak as a value.
#: Plurals are spelled out rather than matched by prefix: `\bCAST` without a closing boundary
#: matches "castigate" under the case-insensitive compare, and a fitness function that cries wolf
#: gets deleted.
_ASSURANCE_VOCABULARY: tuple[str, ...] = (
    *ANALYSIS_METHODS,
    "analysis_method",
    "analysis_methods",
    "assurance_analysis",
    "bowtie",
    "unsafe control action",
    "failure-mode",
    "failure_mode",
    "failure_modes",
)


def _core_source_files() -> list[Path]:
    return sorted(
        path
        for package in _CORE_PACKAGES
        for path in (_REPO_ROOT / package).rglob("*.py")
        if "__pycache__" not in path.parts
    )


@pytest.mark.parametrize("term", _ASSURANCE_VOCABULARY)
def test_the_plug_in_core_never_names_assurance_vocabulary(term: str) -> None:
    # Word-bounded, so `CAST` does not match `broadcast` and `GRC` does not match a longer name.
    pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
    offenders = [
        f"{path.relative_to(_REPO_ROOT)}:{number}"
        for path in _core_source_files()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if pattern.search(line)
    ]
    assert not offenders, (
        f"The plug-in core names the assurance term {term!r} at: {offenders}.\n"
        "Capability protocols and catalogs under src/domain/ontology_representation and "
        "src/domain/modules must stay implementable by a module that has never heard of "
        "assurance. Declare the concept in the owning module's namespace instead — "
        "src/domain/assurance/analysis_scoped_diagram.py is the worked example: a structural "
        "Protocol the module declares and the module's own application code asks for, so a "
        "diagram type opts in by declaring a property and the core learns nothing."
    )


def _assurance_source_files() -> list[Path]:
    return sorted(
        path
        for package in _ASSURANCE_PACKAGES
        for path in (_REPO_ROOT / package).rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _archimate_vocabulary() -> frozenset[str]:
    """ArchiMate's element class names, read from the ontology rather than restated.

    **Class names only — deliberately not the domain names.** `application`, `technology`, `strategy`
    and `business` are ordinary English, and in this codebase they legitimately mean other things: the
    hexagonal *application* layer, a *strategy* for answering a constraint, prose about *technology*
    nodes. Matching them produced four failures and not one leak. A check that cries wolf gets
    deleted, so it holds the terms that cannot be innocent: a compound like
    `strategy-behavior-element` appears in assurance for exactly one reason.

    This still catches the violation that prompted it — `ACTING_CLASSES` named
    `active-structure-element` and `behavior-element` — which is the half that was load-bearing.
    """
    from src.infrastructure.app_bootstrap import get_module_registry

    # The registered module *name*, not the package directory: `archimate_4` on disk registers as
    # `archimate-4-0`, and looking up the wrong one returned an empty set — which made this check
    # skip and assert nothing, the one outcome worse than failing.
    archimate = get_module_registry().all_ontologies()["archimate-4-0"]
    # Compound names only. `internal` and `junction` are also declared classes, and are ordinary
    # English a docstring may use for unrelated reasons — the same false-positive problem the domain
    # names have. A hyphenated class name appears in assurance for exactly one reason.
    classes = frozenset(
        str(name) for name in archimate.element_classes if "-" in str(name)
    )
    assert classes, "the ArchiMate ontology declares no compound element classes; check is vacuous"
    return classes


@pytest.mark.parametrize("term", sorted(_archimate_vocabulary()))
def test_the_assurance_module_never_names_archimate_vocabulary(term: str) -> None:
    """The mirror of the rule above, and the one that was actually broken.

    Deciding which architecture elements an FMEA applies to is assurance's question; *which elements
    act* is ArchiMate's answer to give. Encoding the answer in assurance means a second ontology gets
    the wrong one, and the two drift with nothing failing.
    """
    pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
    offenders = [
        f"{path.relative_to(_REPO_ROOT)}:{number}"
        for path in _assurance_source_files()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if pattern.search(line)
    ]
    assert not offenders, (
        f"the assurance module names the ArchiMate term {term!r} at: {offenders}.\n"
        "Which architecture elements an analysis applies to is assurance's question; which elements "
        "*act* is the ontology's answer. Ask for the resolved set — see "
        "`OntologyCatalog.behavioral_entity_types` and "
        "`domain.ontology_representation.behavioral_elements` — instead of restating the classes or "
        "domains that produce it."
    )

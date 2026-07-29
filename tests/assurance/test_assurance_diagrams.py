"""The catalog of derived assurance diagram projections.

The catalog is derived, not declared: a diagram type is on this surface because it projects its
content from a store graph, it names itself through its own `config.yaml`, and it says there which
analysis methods it draws. What each projection *contains* and how it is *drawn* belong to its
diagram type and are tested there — `tests/diagram_types/test_control_structure_notation.py`,
`tests/diagram_types/test_bowtie_notation.py` — because a live projection and a persisted diagram of
the same type render through one implementation.

**An entry is an analysis crossed with a type, not a type on its own.** A derived diagram belongs to
a unit of work: one control structure per STPA, one matrix per FMEA. Keyed by type alone there is a
single slot per type for the whole store, so a second FMEA has nowhere to put its matrix — which is
the defect this scoping exists to fix.
"""

from __future__ import annotations

from src.application.assurance_diagrams import (
    assurance_surface_diagram_types,
    assurance_surface_diagrams,
    diagram_types_for_method,
)
from src.domain.assurance.analysis_scoped_diagram import AnalysisScopedDiagramType
from src.domain.assurance.assurance_analysis import ANALYSIS_METHODS
from src.domain.modules.catalogs import DiagramTypeCatalog
from src.domain.ontology_representation.ontology_protocol import StoreGraphProjectingDiagramType
from src.infrastructure.app_bootstrap import complete_diagram_type_catalog


def _catalog() -> DiagramTypeCatalog:
    return complete_diagram_type_catalog()


def _analysis(analysis_id: str, name: str, method: str) -> dict[str, object]:
    return {"analysis_id": analysis_id, "name": name, "method": method}


_STPA = _analysis("STPA@1.aaaa.000001", "Key availability", "STPA")
_FMEA = _analysis("FMEA@1.bbbb.000002", "Credential backend", "FMEA")
_SECOND_FMEA = _analysis("FMEA@1.cccc.000003", "Key rotation service", "FMEA")


# ── Method affinity ────────────────────────────────────────────────────────────


def test_every_store_projected_type_declares_the_methods_it_draws() -> None:
    """A type that declared none would be unreachable from every analysis' catalog, which looks
    exactly like a store with nothing in it."""
    registered = _catalog().all_diagram_types()

    for key in assurance_surface_diagram_types(_catalog()):
        diagram_type = registered[key]
        assert isinstance(diagram_type, AnalysisScopedDiagramType), key
        assert diagram_type.analysis_methods, key


def test_declared_methods_come_from_the_assurance_vocabulary() -> None:
    registered = _catalog().all_diagram_types()

    for key in assurance_surface_diagram_types(_catalog()):
        declared = registered[key].analysis_methods  # type: ignore[attr-defined]
        assert declared <= set(ANALYSIS_METHODS), key


def test_the_fmea_matrix_belongs_to_an_fmea_and_not_to_an_stpa() -> None:
    """An STPA reasons about control; the failure-mode grid is about component behaviour. Offering
    it on an STPA would invite the conflation the two methods exist to keep apart."""
    catalog = _catalog()

    assert "fmea-matrix" in diagram_types_for_method(catalog, "FMEA")
    assert "fmea-matrix" not in diagram_types_for_method(catalog, "STPA")


def test_the_uca_matrix_belongs_to_the_methods_that_produce_ucas() -> None:
    catalog = _catalog()

    assert "uca-matrix" in diagram_types_for_method(catalog, "STPA")
    assert "uca-matrix" in diagram_types_for_method(catalog, "CAST")
    assert "uca-matrix" not in diagram_types_for_method(catalog, "FMEA")


def test_an_unknown_method_draws_nothing() -> None:
    assert diagram_types_for_method(_catalog(), "not-a-method") == []


def test_the_types_for_a_method_are_ordered_so_the_overview_is_stable() -> None:
    for method in ANALYSIS_METHODS:
        keys = diagram_types_for_method(_catalog(), method)
        assert keys == sorted(keys)


# ── Catalog entries ────────────────────────────────────────────────────────────


def test_each_analysis_gets_its_own_entry_per_applicable_type() -> None:
    """Two FMEAs mean two matrices. One slot per type is the defect."""
    entries = assurance_surface_diagrams(_catalog(), [_FMEA, _SECOND_FMEA])

    matrices = [e for e in entries if e["diagram_type"] == "fmea-matrix"]
    assert {e["analysis_id"] for e in matrices} == {_FMEA["analysis_id"], _SECOND_FMEA["analysis_id"]}


def test_an_entry_is_identified_by_its_analysis_and_its_type() -> None:
    entry = assurance_surface_diagrams(_catalog(), [_FMEA])[0]

    assert entry["diagram_id"] == f"{_FMEA['analysis_id']}::fmea-matrix"
    assert entry["analysis_id"] == _FMEA["analysis_id"]
    assert entry["diagram_type"] == "fmea-matrix"


def test_an_entry_is_titled_for_its_analysis_not_for_its_type() -> None:
    """A reader with three analyses open already chose the type; what they need is which analysis."""
    entry = assurance_surface_diagrams(_catalog(), [_FMEA])[0]

    assert entry["title"] == "Credential backend"
    assert entry["analysis_name"] == "Credential backend"


def test_an_entry_carries_the_label_and_description_its_type_declares() -> None:
    """Both come from the diagram type, so the overview cannot drift from the type's own name."""
    registered = _catalog().all_diagram_types()

    for entry in assurance_surface_diagrams(_catalog(), [_STPA, _FMEA]):
        declared = registered[entry["diagram_type"]].ui_config
        assert entry["type_label"] == declared.label
        assert entry["description"] == declared.description


def test_an_analysis_whose_method_draws_nothing_contributes_no_entries() -> None:
    """GRC's surface is the risk register; none of the derived diagrams draw obligations."""
    grc = _analysis("GRC@1.dddd.000004", "Q3 controls", "GRC")

    assert diagram_types_for_method(_catalog(), "GRC") == []
    assert assurance_surface_diagrams(_catalog(), [grc]) == []


def test_no_analyses_means_no_entries() -> None:
    """A store with no analyses has no derived diagrams — there is no unit of work to draw."""
    assert assurance_surface_diagrams(_catalog(), []) == []


def test_every_catalogued_entry_names_an_assurance_surface_type() -> None:
    """The catalogued types and the set hidden from the generic diagram browser must agree, or a
    confidential projection could be reachable through the architecture catalog."""
    catalog = _catalog()
    entries = assurance_surface_diagrams(catalog, [_STPA, _FMEA])

    types_used = {e["diagram_type"] for e in entries}
    assert types_used <= set(assurance_surface_diagram_types(catalog))


def test_every_catalogued_entry_can_project_a_store_graph() -> None:
    """The read surface serves a projection by asking its diagram type for one; a catalogued type
    that cannot would 404 at runtime."""
    catalog = _catalog()
    registered = catalog.all_diagram_types()

    for entry in assurance_surface_diagrams(catalog, [_STPA, _FMEA]):
        diagram_type = registered.get(entry["diagram_type"])
        assert diagram_type is not None, entry["diagram_type"]
        assert isinstance(diagram_type, StoreGraphProjectingDiagramType), entry["diagram_type"]


def test_the_surface_is_derived_from_the_capability_not_from_a_module_class() -> None:
    """GSN is assurance work that lives in the repository like any other diagram.

    A surface defined by module class would hide it from the diagram browser, where it is the only
    assurance content a reader without store access can see.
    """
    catalog = _catalog()
    gsn = catalog.find_diagram_type("gsn")

    assert gsn is not None
    assert "gsn" not in assurance_surface_diagram_types(catalog)

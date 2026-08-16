"""Every registered diagram type must present itself, and must do so from its own configuration.

Two defects motivate this. First, `DiagramTypeBase` title-cased the type name when no label was
declared, so `gsn` and `uca-matrix` shipped as "Gsn" and "Uca Matrix" in every picker. Second — worse,
because it is silent — only the config-driven types passed their configuration through
`diagram_type_ui_config_from_mapping`, so five hand-written types could declare a `ui:` block that
nothing ever read. A description is the forcing function here: the fallback can invent a label, but it
can never invent a description, so requiring one is what proves the block is being honoured.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.domain.diagrams.diagram_type_config import DiagramTypeUiConfig
from src.infrastructure.app_bootstrap import complete_diagram_type_catalog

#: What every diagram type presents, resolved from the complete vocabulary so a host without the
#: confidential-store capability tests the same catalog as one with it.
PRESENTATION: dict[str, DiagramTypeUiConfig] = {
    name: diagram_type.ui_config
    for name, diagram_type in complete_diagram_type_catalog().all_diagram_types().items()
}

#: Labels are a curated vocabulary, not a transformation of the key: acronyms and product names do
#: not survive title-casing. Pinning them catches both a regression to the fallback and an
#: unconsidered rename of a label users navigate by.
EXPECTED_LABELS = {
    "activity": "Activity Diagram",
    "archimate-application": "ArchiMate Application",
    "archimate-business": "ArchiMate Business",
    "archimate-implementation": "ArchiMate Implementation & Migration",
    "archimate-layered": "ArchiMate Layered",
    "archimate-motivation": "ArchiMate Motivation",
    "archimate-strategy": "ArchiMate Strategy",
    "archimate-technology": "ArchiMate Technology",
    "bowtie": "Bowtie",
    "c4-component": "C4 Component",
    "c4-container": "C4 Container",
    "c4-deployment": "C4 Deployment",
    "c4-system-context": "C4 System Context",
    "c4-system-landscape": "C4 System Landscape",
    "control-structure": "Control Structure",
    "datatype": "Datatype Diagram",
    "gsn": "GSN Assurance Case",
    "matrix": "Relationship Matrix",
    "sequence": "Sequence Diagram",
    "uca-matrix": "UCA Matrix",
    "fmea-matrix": "FMEA Matrix",
}


@pytest.mark.verifies("REQ@1712870400.Ii5Jj5")
def test_every_registered_type_has_a_curated_label() -> None:
    assert {name: ui.label for name, ui in PRESENTATION.items()} == EXPECTED_LABELS


@pytest.mark.parametrize("name", sorted(PRESENTATION))
def test_every_registered_type_describes_itself(name: str) -> None:
    """An empty description reaches the create-diagram picker as a blank line under the type's name."""
    description = PRESENTATION[name].description

    assert description, f"{name} declares no ui.description"
    assert description.strip() == description
    assert description.endswith("."), f"{name}: a description reads as a sentence"


@pytest.mark.parametrize("name", sorted(PRESENTATION))
def test_a_label_is_never_the_title_cased_fallback(name: str) -> None:
    """The fallback is for synthetic configs in tests; a registered type states its own name."""
    fallback = name.replace("-", " ").title()

    assert PRESENTATION[name].label != fallback or fallback in EXPECTED_LABELS.values()


def test_presentation_comes_from_each_type_s_own_config_file() -> None:
    """The declaration has to live with the type, or the base class is reading nothing.

    Types that assemble configuration from several sources set `_ui_config` themselves; they still
    declare the text in their own `config.yaml`, which is what this reads.
    """
    package_root = Path("src/diagram_types")
    declared: dict[str, tuple[str, str]] = {}
    for config_path in package_root.rglob("config.yaml"):
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        ui = config.get("ui") or {}
        declared[str(config["name"])] = (str(ui.get("label", "")), str(ui.get("description", "")))

    assert set(declared) == set(PRESENTATION), "a registered type has no config.yaml of its own"
    for name, (label, description) in declared.items():
        assert label == PRESENTATION[name].label, f"{name}: declared label is not the one served"
        assert description == PRESENTATION[name].description, f"{name}: declared description is not served"

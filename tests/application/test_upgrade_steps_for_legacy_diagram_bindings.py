"""The edges of the steps that repair a legacy diagram's bindings: what they leave alone, and why.

The whole-repository case — an upgrade leaving the repository verifying clean — is asserted in
`tests/cli/test_an_upgrade_repairs_what_earlier_writes_left.py`. These are the cases a step must not
guess at: a drawing two model relations fit, an id whose host this repository does not hold.
"""

from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]

from src.application.modeling.diagram_identities import entity_by_alias
from src.application.repository_upgrade.steps.drawn_relations_bound import DrawnRelationsBoundStep
from src.application.repository_upgrade.steps.entity_list_names_elements import EntityListNamesElementsStep
from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.repository_upgrade.fs_adapter import FilesystemRepoUpgradeView, FilesystemRepoUpgradeWriter

APP = "APP@1700000001.Engine1.engine"
SSW = "SSW@1700000002.Toolkt2.toolkit"
VIEW = "ARC@1700000003.View003.view"


def _outgoing(root: Path, source: str, *declarations: tuple[str, str]) -> None:
    sections = "\n".join(f"### {conn_type} → {target}\n\nDescribed.\n" for conn_type, target in declarations)
    path = root / "model" / f"{source}.outgoing.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nsource-entity: {source}\nversion: 0.1.0\nstatus: active\nlast-updated: '2026-01-01'\n---\n\n"
        f"<!-- §connections -->\n\n{sections}",
        encoding="utf-8",
    )


def _diagram(root: Path, frontmatter: dict[str, object], body: str) -> Path:
    path = root / "diagram-catalog" / "diagrams" / f"{VIEW}.puml"
    path.parent.mkdir(parents=True, exist_ok=True)
    head = yaml.safe_dump(
        {"artifact-id": VIEW, "artifact-type": "diagram", "name": "View", "diagram-type": "archimate-layered",
         **frontmatter},
        sort_keys=False,
    )
    path.write_text(f"---\n{head}---\n@startuml\ntitle View\n{body}\n@enduml\n", encoding="utf-8")
    return path


NESTED = (
    'rectangle "Engine" <<application_component>> as APP_Engine1 {\n'
    '  rectangle "Toolkit" <<system_software>> as SSW_Toolkt2\n'
    "}"
)


def _applied(step: object, root: Path) -> list:
    view, writer = FilesystemRepoUpgradeView(root), FilesystemRepoUpgradeWriter(root)
    findings = step.detect(view)  # type: ignore[attr-defined]
    step.apply(view, writer, [f for f in findings if f.auto_migratable])  # type: ignore[attr-defined]
    return findings


def test_a_nesting_two_model_relations_fit_is_reported_and_left(tmp_path: Path) -> None:
    _outgoing(tmp_path, SSW, ("archimate-serving", APP))
    _outgoing(tmp_path, APP, ("archimate-composition", SSW))
    path = _diagram(tmp_path, {"entity-ids-used": [APP, SSW], "connection-ids-used": []}, NESTED)
    before = path.read_text(encoding="utf-8")

    findings = _applied(DrawnRelationsBoundStep(), tmp_path)

    (finding,) = findings
    assert not finding.auto_migratable
    assert "archimate-serving" in finding.manual_instructions and "archimate-composition" in finding.manual_instructions
    assert path.read_text(encoding="utf-8") == before


def test_a_typed_arrow_names_the_one_it_draws(tmp_path: Path) -> None:
    _outgoing(tmp_path, SSW, ("archimate-serving", APP), ("archimate-realization", APP))
    path = _diagram(
        tmp_path, {"entity-ids-used": [APP, SSW]},
        'rectangle "E" <<application_component>> as APP_Engine1\n'
        'rectangle "T" <<system_software>> as SSW_Toolkt2\n'
        "SSW_Toolkt2 --> APP_Engine1 : <<serving>>",
    )

    _applied(DrawnRelationsBoundStep(), tmp_path)

    stated = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert stated["connection-ids-used"] == ["SSW@1700000002.Toolkt2---APP@1700000001.Engine1@@archimate-serving"]


def test_a_statement_whose_host_is_elsewhere_is_left_for_the_verifier(tmp_path: Path) -> None:
    elsewhere = "ARC@1700000009.Other09.other#occurrence/APP_Engine1_x2"
    own = f"{VIEW}#occurrence/APP_Engine1_x2"
    path = _diagram(
        tmp_path, {"entity-ids-used": [APP, elsewhere, own]}, 'rectangle "E" <<application_component>> as APP_Engine1',
    )

    _applied(EntityListNamesElementsStep(), tmp_path)

    assert parse_frontmatter(path.read_text(encoding="utf-8"))["entity-ids-used"] == [APP, elsewhere]


def test_an_occurrence_alias_stands_for_the_element_it_draws_again() -> None:
    stated = {
        "entity-ids-used": [APP, f"{VIEW}#occurrence/APP_Engine1_x2"],
        "diagram-entities": {"occurrence": [{"id": "APP_Engine1_x2"}]},
        "bindings": [{"id": "b", "subject": {"kind": "entity", "id": "APP_Engine1_x2"},
                      "correspondence_kind": "represents", "target": {"entity_id": APP}}],
    }

    aliases = entity_by_alias(stated)

    assert aliases["APP_Engine1"] == "APP@1700000001.Engine1"
    assert aliases["APP_Engine1__2"] == "APP@1700000001.Engine1"
    assert "ARC_View003" not in aliases, "a statement's id names no element"

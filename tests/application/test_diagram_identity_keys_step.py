"""The upgrade that gives each diagram grouping an id and re-keys each edge label by its relation.

On repositories the tests write: what it changes, that it changes nothing else, that a second run
changes nothing at all, and that it leaves alone — and names — every label it cannot settle without
guessing.
"""

from __future__ import annotations

from pathlib import Path

from src.application.repository_upgrade.steps.diagram_identity_keys import DiagramIdentityKeysStep
from src.application.verification._verifier_rules_edge_labels import check_edge_label_overrides
from src.application.verification.artifact_verifier_types import VerificationResult
from src.domain.diagrams.authored_groupings import check_groupings, grouping_ids, with_grouping_ids
from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.repository_upgrade.fs_adapter import (
    FilesystemRepoUpgradeView,
    FilesystemRepoUpgradeWriter,
)
from tests.support.repository_upgrade_conformance import assert_step_preserves_unknown_content

_PORTAL = "APP@1700000001.aaaaaa.portal"
_LEDGER = "APP@1700000002.bbbbbb.ledger"
_SERVING = "APP@1700000001.aaaaaa---APP@1700000002.bbbbbb@@archimate-serving"
_FLOW = "APP@1700000001.aaaaaa---APP@1700000002.bbbbbb@@archimate-flow"
_WHERE = "diagram-catalog/diagrams/ARC@1700000000.dddddd.a-view.puml"
_BODY = "@startuml a-view\ntitle A View\nAPP_aaaaaa --> APP_bbbbbb\n@enduml\n"


def _diagram(root: Path, statements: str, *, where: str = _WHERE) -> Path:
    path = root / where
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nartifact-id: ARC@1700000000.dddddd.a-view\nartifact-type: diagram\nname: A View\n"
        "version: 0.1.0\nstatus: draft\ndiagram-type: archimate-application\n"
        f"entity-ids-used:\n- {_PORTAL}\n- {_LEDGER}\n{statements}last-updated: '2026-01-01T00:00:00Z'\n---\n{_BODY}",
        encoding="utf-8",
    )
    return path


def _upgrade(root: Path) -> list:
    step = DiagramIdentityKeysStep()
    view = FilesystemRepoUpgradeView(root)
    findings = step.detect(view)
    step.apply(view, FilesystemRepoUpgradeWriter(root), [finding for finding in findings if finding.auto_migratable])
    return findings


_GROUPED = (
    f"authored-groupings:\n- label: Front\n  stereotype: ''\n  entity-ids:\n  - {_PORTAL}\n"
    f"  groups:\n  - label: Inner\n    entity-ids:\n    - {_LEDGER}\n- label: Back\n  entity-ids: []\n"
)


class TestGroupingIds:
    def test_every_grouping_at_any_depth_gains_an_id_and_nothing_else_about_it_changes(self, tmp_path: Path) -> None:
        path = _diagram(tmp_path, _GROUPED)
        before = parse_frontmatter(path.read_text(encoding="utf-8"))

        (finding,) = _upgrade(tmp_path)

        assert finding.auto_migratable and "3 grouping(s)" in finding.description
        after = parse_frontmatter(path.read_text(encoding="utf-8"))
        ids = grouping_ids(after["authored-groupings"])
        assert len(ids) == 3 and len(set(ids)) == 3
        assert check_groupings(after["authored-groupings"]) == []
        without_ids = [
            {key: ([{k: v for k, v in sub.items() if k != "id"} for sub in value] if key == "groups" else value)
             for key, value in group.items() if key != "id"}
            for group in after["authored-groupings"]
        ]
        assert without_ids == before["authored-groupings"]
        assert {key: value for key, value in after.items() if key != "authored-groupings"} == {
            key: value for key, value in before.items() if key != "authored-groupings"
        }

    def test_the_ids_are_the_ones_a_write_through_the_tools_gives_the_same_statement(self, tmp_path: Path) -> None:
        """So an upgrade in one checkout and a write in another agree on which box is which."""
        path = _diagram(tmp_path, _GROUPED)
        stated = parse_frontmatter(path.read_text(encoding="utf-8"))["authored-groupings"]

        _upgrade(tmp_path)

        upgraded = parse_frontmatter(path.read_text(encoding="utf-8"))["authored-groupings"]
        assert upgraded == with_grouping_ids(stated, diagram_id="ARC@1700000000.dddddd")

    def test_a_grouping_that_has_an_id_keeps_it(self, tmp_path: Path) -> None:
        path = _diagram(tmp_path, "authored-groupings:\n- id: g-Kept01\n  label: Front\n- label: Back\n")

        _upgrade(tmp_path)

        ids = grouping_ids(parse_frontmatter(path.read_text(encoding="utf-8"))["authored-groupings"])
        assert ids[0] == "g-Kept01" and len(ids) == 2

    def test_a_second_run_finds_nothing_and_writes_nothing(self, tmp_path: Path) -> None:
        path = _diagram(
            tmp_path, _GROUPED + f"connection-ids-used:\n- {_SERVING}\nedge-labels:\n  APP_aaaaaa:APP_bbbbbb: reads\n"
        )
        _upgrade(tmp_path)
        once = path.read_bytes()

        assert _upgrade(tmp_path) == []
        assert path.read_bytes() == once

    def test_everything_the_step_has_no_opinion_about_is_left_byte_for_byte(self, tmp_path: Path) -> None:
        marker = "# a note somebody left, and a field nobody registered"
        path = _diagram(tmp_path, f"{marker}\nx-of-ours:\n  kept: [1, 2,   3]\n" + _GROUPED)
        before = path.read_text(encoding="utf-8").split("\n")
        step = DiagramIdentityKeysStep()

        assert_step_preserves_unknown_content(
            step, FilesystemRepoUpgradeView(tmp_path), FilesystemRepoUpgradeWriter(tmp_path),
            location=_WHERE, unknown_marker=marker,
        )

        after = path.read_text(encoding="utf-8").split("\n")
        added = [line for line in after if line not in before]
        assert all(line.strip().startswith(("- id: g-", "label:")) for line in added), added
        assert [line for line in before if line not in after and "label:" not in line] == []
        assert "  kept: [1, 2,   3]" in after and _BODY.strip() in "\n".join(after)

    def test_a_file_that_is_not_a_diagram_is_not_touched(self, tmp_path: Path) -> None:
        entity = tmp_path / "model" / "APP@1.x.md"
        entity.parent.mkdir(parents=True)
        entity.write_text("---\nartifact-id: APP@1.x\nartifact-type: application-component\n"
                          "authored-groupings:\n- label: Odd\n---\nbody\n", encoding="utf-8")

        assert _upgrade(tmp_path) == []


def _labels(path: Path) -> dict:
    return parse_frontmatter(path.read_text(encoding="utf-8")).get("edge-labels") or {}


def _still_dangling(path: Path) -> list[str]:
    result = VerificationResult(path=path, file_type="diagram")
    check_edge_label_overrides(parse_frontmatter(path.read_text(encoding="utf-8")), result, str(path))
    return [issue.message for issue in result.issues]


class TestEdgeLabelKeys:
    def test_a_pair_one_relation_fits_is_re_keyed_by_that_relation(self, tmp_path: Path) -> None:
        path = _diagram(tmp_path, f"connection-ids-used:\n- {_SERVING}\nedge-labels:\n  APP_aaaaaa:APP_bbbbbb: reads\n")

        (finding,) = _upgrade(tmp_path)

        assert finding.auto_migratable and "re-key 1 edge label" in (finding.rewrite_summary or "")
        assert _labels(path) == {_SERVING: "reads"}
        assert _still_dangling(path) == []

    def test_a_pair_two_relations_fit_is_reported_and_left_exactly_as_it_is(self, tmp_path: Path) -> None:
        """The case the old key could not express, so the upgrade cannot know which was meant."""
        path = _diagram(
            tmp_path, f"connection-ids-used:\n- {_SERVING}\n- {_FLOW}\nedge-labels:\n  APP_aaaaaa:APP_bbbbbb: reads\n"
        )
        before = path.read_bytes()

        (finding,) = _upgrade(tmp_path)

        assert not finding.auto_migratable
        assert "fits 2 relations" in finding.description
        assert _SERVING in (finding.manual_instructions or "") and _FLOW in (finding.manual_instructions or "")
        assert path.read_bytes() == before

    def test_a_pair_no_relation_fits_is_reported_and_left(self, tmp_path: Path) -> None:
        path = _diagram(tmp_path, f"connection-ids-used:\n- {_SERVING}\nedge-labels:\n  APP_aaaaaa:APP_zzzzzz: reads\n")
        before = path.read_bytes()

        (finding,) = _upgrade(tmp_path)

        assert not finding.auto_migratable and "fits no relation" in finding.description
        assert path.read_bytes() == before

    def test_the_settled_labels_move_and_the_unsettled_one_stays_beside_them(self, tmp_path: Path) -> None:
        third = "APP@1700000003.cccccc.archive"
        to_archive = "APP@1700000002.bbbbbb---APP@1700000003.cccccc@@archimate-flow"
        path = _diagram(
            tmp_path,
            f"- {third}\nconnection-ids-used:\n- {_SERVING}\n- {_FLOW}\n- {to_archive}\n"
            "edge-labels:\n  APP_aaaaaa:APP_bbbbbb: which one\n  APP_bbbbbb:APP_cccccc: files\n",
        )

        findings = _upgrade(tmp_path)

        assert sorted(finding.auto_migratable for finding in findings) == [False, True]
        assert _labels(path) == {"APP_aaaaaa:APP_bbbbbb": "which one", to_archive: "files"}

    def test_the_arrow_at_a_further_occurrence_is_keyed_with_its_instances(self, tmp_path: Path) -> None:
        path = _diagram(
            tmp_path,
            f"connection-ids-used:\n- {_SERVING}\n"
            f"diagram-entities:\n  occurrence:\n  - id: portal-again\n    backing_entity_id: {_PORTAL}\n"
            f"connections:\n- artifact_id: {_SERVING}\n- artifact_id: {_SERVING}\n  source-occurrence: portal-again\n"
            "edge-labels:\n  APP_aaaaaa__2:APP_bbbbbb: from the copy\n  APP_aaaaaa:APP_bbbbbb: from the first\n",
        )

        _upgrade(tmp_path)

        assert _labels(path) == {
            f"{_SERVING}@portal-again>APP@1700000002.bbbbbb": "from the copy", _SERVING: "from the first",
        }
        assert _still_dangling(path) == []

    def test_an_occurrence_is_found_where_a_stored_diagram_keeps_it_in_the_bindings_block(self, tmp_path: Path) -> None:
        """What a write through the tools leaves behind: the occurrence names no entity itself."""
        path = _diagram(
            tmp_path,
            f"connection-ids-used:\n- {_SERVING}\n"
            "diagram-entities:\n  occurrence:\n  - id: portal-again\n"
            f"connections:\n- artifact_id: {_SERVING}\n  source-occurrence: portal-again\n"
            "bindings:\n- id: b1\n  subject:\n    kind: entity\n    id: portal-again\n"
            f"  correspondence_kind: represents\n  target:\n    entity_id: {_PORTAL}\n"
            "edge-labels:\n  APP_aaaaaa__2:APP_bbbbbb: from the copy\n",
        )

        _upgrade(tmp_path)

        assert _labels(path) == {f"{_SERVING}@portal-again>APP@1700000002.bbbbbb": "from the copy"}
        assert _still_dangling(path) == []

    def test_a_relation_drawn_against_its_direction_is_still_the_one_the_pair_meant(self, tmp_path: Path) -> None:
        path = _diagram(
            tmp_path, f"connection-ids-used:\n- {_SERVING}\nedge-labels:\n  APP_bbbbbb:APP_aaaaaa: is read by\n"
        )

        _upgrade(tmp_path)

        assert _labels(path) == {_SERVING: "is read by"}

    def test_a_connection_the_diagram_holds_is_keyed_by_its_own_id_where_its_rows_state_their_aliases(
        self, tmp_path: Path
    ) -> None:
        path = _diagram(
            tmp_path,
            "diagram-entities:\n  container:\n  - id: svc\n    alias: C_svc\n  - id: db\n    alias: C_db\n"
            "connections:\n- source: svc\n  target: db\n  label: reads\n"
            "edge-labels:\n  C_svc:C_db: Reads and writes\n",
        )

        _upgrade(tmp_path)

        assert _labels(path) == {"svc::db": "Reads and writes"}

    def test_a_held_connection_whose_aliases_the_diagram_does_not_state_is_reported(self, tmp_path: Path) -> None:
        path = _diagram(
            tmp_path,
            "diagram-entities:\n  container:\n  - id: svc\n  - id: db\n"
            "connections:\n- source: svc\n  target: db\n  label: reads\n"
            "edge-labels:\n  C_svc_0:C_db_1: Reads and writes\n",
        )
        before = path.read_bytes()

        (finding,) = _upgrade(tmp_path)

        assert not finding.auto_migratable and "artifact_edit_diagram" in (finding.manual_instructions or "")
        assert path.read_bytes() == before

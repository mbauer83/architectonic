"""The ordinal-declaration upgrade step: three cases, and a second run that changes nothing.

The case worth care is drift. An attribute schema on disk belongs to the operator, and its enum may
differ from the shipped one either because they customised it or because a release retired members.
Either way the step reports and rewrites nothing: ranking a list this software did not define would
assign an order nobody chose. Only a byte-for-byte match with the shipped members is migrated.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.application.repository_upgrade.steps.ordinal_enum_declaration import (
    OrdinalEnumDeclarationStep,
)
from src.domain.ontology_representation.attribute_scales import ORDINAL_SCALE, SCALE_KEYWORD
from src.domain.repository.repo_default_schemata import DEFAULT_SCHEMATA
from src.infrastructure.repository_upgrade.fs_adapter import (
    FilesystemRepoUpgradeView,
    FilesystemRepoUpgradeWriter,
)

_RISK_SCHEMA = "attributes.risk.schema.json"


def _shipped_members(filename: str, prop: str) -> list[str]:
    return list(DEFAULT_SCHEMATA[filename]["properties"][prop]["enum"])


def _write_schema(root: Path, filename: str, schema: dict[str, Any]) -> Path:
    path = root / ".arch-repo" / "schemata" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    return path


def _unranked_risk_schema(*, members: list[str] | None = None) -> dict[str, Any]:
    """The shipped risk schema with the rank marker stripped from `impact`."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": _RISK_SCHEMA,
        "type": "object",
        "required": [],
        "properties": {
            "impact": {
                "type": "string",
                "enum": members if members is not None else _shipped_members(_RISK_SCHEMA, "impact"),
            },
        },
        "additionalProperties": True,
    }


def _run(root: Path) -> tuple[list[Any], list[Any]]:
    step = OrdinalEnumDeclarationStep()
    view = FilesystemRepoUpgradeView(root)
    findings = step.detect(view)
    applied = step.apply(view, FilesystemRepoUpgradeWriter(root), findings)
    return findings, applied


def _impact(root: Path) -> dict[str, Any]:
    text = (root / ".arch-repo" / "schemata" / _RISK_SCHEMA).read_text(encoding="utf-8")
    return dict(json.loads(text)["properties"]["impact"])


class TestAMatchingEnumIsMigrated:
    def test_the_missing_marker_is_detected(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, _RISK_SCHEMA, _unranked_risk_schema())

        findings, _ = _run(tmp_path)

        assert [f.finding_id for f in findings] == [f"unranked-enum:{_RISK_SCHEMA}:impact"]
        assert findings[0].auto_migratable

    def test_the_marker_is_added(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, _RISK_SCHEMA, _unranked_risk_schema())

        _, applied = _run(tmp_path)

        assert [a.outcome for a in applied] == ["applied"]
        assert _impact(tmp_path)[SCALE_KEYWORD] == ORDINAL_SCALE

    def test_the_members_are_left_exactly_as_they_were(self, tmp_path: Path) -> None:
        """Adding a rank must not reorder or edit the vocabulary it ranks."""
        _write_schema(tmp_path, _RISK_SCHEMA, _unranked_risk_schema())

        _run(tmp_path)

        assert _impact(tmp_path)["enum"] == _shipped_members(_RISK_SCHEMA, "impact")


class TestAnAlreadyMarkedEnumIsLeftAlone:
    def test_nothing_is_detected(self, tmp_path: Path) -> None:
        schema = _unranked_risk_schema()
        schema["properties"]["impact"][SCALE_KEYWORD] = ORDINAL_SCALE
        _write_schema(tmp_path, _RISK_SCHEMA, schema)

        findings, _ = _run(tmp_path)

        assert findings == []

    def test_a_second_run_changes_no_bytes(self, tmp_path: Path) -> None:
        """The property an upgrade step is most often missing: idempotence at the byte level."""
        path = _write_schema(tmp_path, _RISK_SCHEMA, _unranked_risk_schema())
        _run(tmp_path)
        after_first = path.read_bytes()

        _run(tmp_path)

        assert path.read_bytes() == after_first


class TestADriftedEnumIsReportedAndNotRewritten:
    def test_retired_members_make_it_a_manual_finding(self, tmp_path: Path) -> None:
        """Drift is not always the operator's doing — a repo can carry members a release retired."""
        members = [*_shipped_members(_RISK_SCHEMA, "impact"), "apocalyptic"]
        _write_schema(tmp_path, _RISK_SCHEMA, _unranked_risk_schema(members=members))

        findings, _ = _run(tmp_path)

        assert not findings[0].auto_migratable
        assert findings[0].severity == "error"

    def test_the_finding_says_which_members_differ_and_in_which_direction(self, tmp_path: Path) -> None:
        """"Your file is different" leaves a reader to diff it themselves."""
        members = [m for m in _shipped_members(_RISK_SCHEMA, "impact") if m != "minor"] + ["slight"]
        _write_schema(tmp_path, _RISK_SCHEMA, _unranked_risk_schema(members=members))

        findings, _ = _run(tmp_path)

        assert "slight" in findings[0].description
        assert "minor" in findings[0].description

    def test_a_reordered_enum_is_drift_too(self, tmp_path: Path) -> None:
        """Same members, different ranks — the most dangerous kind to mark silently."""
        members = list(reversed(_shipped_members(_RISK_SCHEMA, "impact")))
        _write_schema(tmp_path, _RISK_SCHEMA, _unranked_risk_schema(members=members))

        findings, _ = _run(tmp_path)

        assert not findings[0].auto_migratable
        assert "different order" in findings[0].description

    def test_nothing_is_written(self, tmp_path: Path) -> None:
        members = [*_shipped_members(_RISK_SCHEMA, "impact"), "apocalyptic"]
        path = _write_schema(tmp_path, _RISK_SCHEMA, _unranked_risk_schema(members=members))
        before = path.read_bytes()

        _, applied = _run(tmp_path)

        assert path.read_bytes() == before
        assert [a.outcome for a in applied] == ["skipped"]

    def test_the_manual_instructions_name_the_shipped_vocabulary(self, tmp_path: Path) -> None:
        members = [*_shipped_members(_RISK_SCHEMA, "impact"), "apocalyptic"]
        _write_schema(tmp_path, _RISK_SCHEMA, _unranked_risk_schema(members=members))

        findings, _ = _run(tmp_path)

        assert findings[0].manual_instructions
        assert "catastrophic" in findings[0].manual_instructions


class TestFilesTheStepMustNotTouch:
    def test_an_absent_schema_is_not_a_finding(self, tmp_path: Path) -> None:
        """The ensure-missing step ships it, marker already present."""
        (tmp_path / ".arch-repo" / "schemata").mkdir(parents=True)

        findings, _ = _run(tmp_path)

        assert findings == []

    def test_a_malformed_schema_is_left_to_the_schema_scan(self, tmp_path: Path) -> None:
        path = tmp_path / ".arch-repo" / "schemata" / _RISK_SCHEMA
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")

        findings, _ = _run(tmp_path)

        assert findings == []
        assert path.read_text(encoding="utf-8") == "{not json"


class TestTheLossSchemaNeedsNoStepOfItsOwn:
    """Recorded verdict: the new `attributes.loss.schema.json` default reaches an existing repo
    through the ensure-missing step, which already ships defaults a repo lacks. A dedicated step
    would duplicate that, and two steps writing one file is how they come to disagree."""

    def test_the_loss_schema_is_a_shipped_default(self) -> None:
        assert "attributes.loss.schema.json" in DEFAULT_SCHEMATA

    def test_an_existing_repo_receives_it_with_the_rank_already_present(self, tmp_path: Path) -> None:
        from src.application.repository_upgrade.steps.default_schemata_ensure import (
            DefaultSchemataEnsureStep,
        )

        (tmp_path / ".arch-repo" / "schemata").mkdir(parents=True)
        step = DefaultSchemataEnsureStep()
        view = FilesystemRepoUpgradeView(tmp_path)
        step.apply(view, FilesystemRepoUpgradeWriter(tmp_path), step.detect(view))

        written = json.loads(
            (tmp_path / ".arch-repo" / "schemata" / "attributes.loss.schema.json").read_text()
        )

        assert written["properties"]["severity"][SCALE_KEYWORD] == ORDINAL_SCALE

    def test_the_ordinal_step_then_finds_nothing_to_do_for_it(self, tmp_path: Path) -> None:
        """The two steps must not both claim the same file."""
        from src.application.repository_upgrade.steps.default_schemata_ensure import (
            DefaultSchemataEnsureStep,
        )

        (tmp_path / ".arch-repo" / "schemata").mkdir(parents=True)
        ensure = DefaultSchemataEnsureStep()
        view = FilesystemRepoUpgradeView(tmp_path)
        ensure.apply(view, FilesystemRepoUpgradeWriter(tmp_path), ensure.detect(view))

        findings, _ = _run(tmp_path)

        assert [f for f in findings if "loss" in f.finding_id] == []

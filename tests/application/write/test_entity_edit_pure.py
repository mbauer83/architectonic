"""Tests for pure helpers in entity_edit.py and _entity_edit_support.py.

Covers: _bump_version (entity_edit.py), merge_fields and count_rename_referrers
(_entity_edit_support.py).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from src.infrastructure.write.artifact_write._entity_edit_support import (
    _UNSET,
    count_rename_referrers,
    merge_fields,
)
from src.infrastructure.write.artifact_write.entity_edit import _bump_version
from src.infrastructure.write.artifact_write.parse_existing import ParsedEntity

# ---------------------------------------------------------------------------
# _bump_version
# ---------------------------------------------------------------------------


class TestBumpVersion:
    def test_draft_to_active_bumps_minor(self) -> None:
        assert _bump_version("0.1.0", "draft") == "0.2.0"

    def test_active_to_deprecated_bumps_major(self) -> None:
        assert _bump_version("1.5.3", "active") == "2.0.0"

    def test_returns_unchanged_when_not_semver(self) -> None:
        assert _bump_version("bad", "draft") == "bad"

    def test_returns_unchanged_when_two_parts(self) -> None:
        assert _bump_version("1.0", "draft") == "1.0"

    def test_draft_with_major_gt_zero(self) -> None:
        assert _bump_version("2.3.0", "draft") == "2.4.0"


# ---------------------------------------------------------------------------
# merge_fields
# ---------------------------------------------------------------------------


def _parsed(*, name="Orig", version="0.1.0", status="draft", keywords=None) -> ParsedEntity:
    return ParsedEntity(
        frontmatter={
            "name": name,
            "version": version,
            "status": status,
            "keywords": keywords,
        },
        summary="Original summary",
        properties={"key": "val"},
        notes="Original notes",
        display_section_id="disp",
        display_content="",
        raw_text="",
    )


class TestMergeFields:
    def test_uses_new_name_when_provided(self) -> None:
        merged = merge_fields(_parsed(), name="New Name", version=None, status=None,
                              keywords=_UNSET, summary=_UNSET, properties=_UNSET, attribute_types=_UNSET, notes=_UNSET)
        assert merged.name == "New Name"

    def test_keeps_current_name_when_none(self) -> None:
        merged = merge_fields(_parsed(name="Keep"), name=None, version=None, status=None,
                              keywords=_UNSET, summary=_UNSET, properties=_UNSET, attribute_types=_UNSET, notes=_UNSET)
        assert merged.name == "Keep"

    def test_uses_new_version_when_provided(self) -> None:
        merged = merge_fields(_parsed(), name=None, version="1.0.0", status=None,
                              keywords=_UNSET, summary=_UNSET, properties=_UNSET, attribute_types=_UNSET, notes=_UNSET)
        assert merged.version == "1.0.0"

    def test_uses_new_status_when_provided(self) -> None:
        merged = merge_fields(_parsed(), name=None, version=None, status="active",
                              keywords=_UNSET, summary=_UNSET, properties=_UNSET, attribute_types=_UNSET, notes=_UNSET)
        assert merged.status == "active"

    def test_keeps_parsed_summary_when_unset(self) -> None:
        parsed = _parsed()
        merged = merge_fields(parsed, name=None, version=None, status=None,
                              keywords=_UNSET, summary=_UNSET, properties=_UNSET, attribute_types=_UNSET, notes=_UNSET)
        assert merged.summary == parsed.summary

    def test_uses_new_summary_when_provided(self) -> None:
        merged = merge_fields(_parsed(), name=None, version=None, status=None,
                              keywords=_UNSET, summary="New summary",
                              properties=_UNSET, attribute_types=_UNSET, notes=_UNSET)
        assert merged.summary == "New summary"

    def test_none_summary_sets_to_none(self) -> None:
        merged = merge_fields(_parsed(), name=None, version=None, status=None,
                              keywords=_UNSET, summary=None, properties=_UNSET, attribute_types=_UNSET, notes=_UNSET)
        assert merged.summary is None

    def test_keeps_parsed_properties_when_unset(self) -> None:
        parsed = _parsed()
        merged = merge_fields(parsed, name=None, version=None, status=None,
                              keywords=_UNSET, summary=_UNSET, properties=_UNSET, attribute_types=_UNSET, notes=_UNSET)
        assert merged.properties == {"key": "val"}

    def test_uses_new_keywords_when_provided(self) -> None:
        merged = merge_fields(_parsed(), name=None, version=None, status=None,
                              keywords=["a", "b"], summary=_UNSET,
                              properties=_UNSET, attribute_types=_UNSET, notes=_UNSET)
        assert merged.keywords == ["a", "b"]


# ---------------------------------------------------------------------------
# count_rename_referrers
# ---------------------------------------------------------------------------


def _git_init(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=path, check=True, capture_output=True)
    (path / ".gitkeep").write_text("")
    subprocess.run(["git", "add", ".gitkeep"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


class TestCountRenameReferrers:
    def test_zero_when_no_outgoing_files(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        _git_init(repo)
        own_outgoing = repo / "model" / "ENT@1.x.y.outgoing.md"
        count = count_rename_referrers(repo, "ENT@1.x.y", own_outgoing)
        assert count == 0

    def test_counts_own_outgoing_when_exists(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        _git_init(repo)
        model = repo / "model" / "domain"
        model.mkdir(parents=True)
        own_outgoing = model / "ENT@1.x.y.outgoing.md"
        own_outgoing.write_text("artifact-id: ENT@1.x.y\n")
        count = count_rename_referrers(repo, "ENT@1.x.y", own_outgoing)
        assert count == 1  # only own file

    def test_counts_foreign_referrer(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        _git_init(repo)
        model = repo / "model" / "domain"
        model.mkdir(parents=True)
        own_outgoing = model / "ENT@1.x.y.outgoing.md"
        own_outgoing.write_text("source: ENT@1.x.y\n")
        referrer = model / "ENT@2.a.b.outgoing.md"
        referrer.write_text("target: ENT@1.x.y\n")
        count = count_rename_referrers(repo, "ENT@1.x.y", own_outgoing)
        assert count == 2  # own + referrer


class TestAttributeMapsArePatchedNotReplaced:
    """Setting one attribute must not drop the others.

    The tool contract is "pass only what changes". Honouring that for `name` while replacing the
    whole attribute map one level down is the trap it reads as protecting against: a caller adding a
    classification silently erased the format, lifecycle and table list already recorded, and had to
    read the entity first and resend values it never meant to touch.
    """

    def _merged(self, **overrides: object):  # type: ignore[no-untyped-def]
        fields: dict[str, object] = dict(
            name=None, version=None, status=None, keywords=_UNSET, summary=_UNSET,
            properties=_UNSET, attribute_types=_UNSET, notes=_UNSET,
        )
        fields.update(overrides)
        return merge_fields(_parsed(), **fields)  # type: ignore[arg-type]

    def test_a_new_attribute_keeps_the_ones_already_recorded(self) -> None:
        merged = self._merged(properties={"Sensitivity": "Confidential"})

        assert merged.properties == {"key": "val", "Sensitivity": "Confidential"}

    def test_an_existing_attribute_is_overwritten_by_name(self) -> None:
        merged = self._merged(properties={"key": "replaced"})

        assert merged.properties == {"key": "replaced"}

    def test_a_null_value_removes_that_attribute(self) -> None:
        """The only way a patch can express deletion, so it has to be asked for explicitly."""
        merged = self._merged(properties={"key": None})

        assert merged.properties is None

    def test_removing_one_of_several_leaves_the_rest(self) -> None:
        merged = merge_fields(
            _parsed(), name=None, version=None, status=None, keywords=_UNSET, summary=_UNSET,
            properties={"other": "kept", "key": None}, attribute_types=_UNSET, notes=_UNSET,
        )

        assert merged.properties == {"other": "kept"}

    def test_an_empty_map_changes_nothing(self) -> None:
        assert self._merged(properties={}).properties == {"key": "val"}

    def test_omitting_properties_still_keeps_them(self) -> None:
        assert self._merged().properties == {"key": "val"}

    def test_declared_attribute_types_are_patched_the_same_way(self) -> None:
        """Otherwise declaring one type erases the others, and typed values decode as text."""
        parsed = _parsed()
        parsed.frontmatter["attribute-types"] = {"Existing": "list"}

        merged = merge_fields(
            parsed, name=None, version=None, status=None, keywords=_UNSET, summary=_UNSET,
            properties=_UNSET, attribute_types={"Added": "string"}, notes=_UNSET,
        )

        assert merged.attribute_types == {"Existing": "list", "Added": "string"}

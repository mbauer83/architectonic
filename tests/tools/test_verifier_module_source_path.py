"""Tests for the W160 Module source-path existence check (WU-16)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.verification._verifier_rules_schema import (
    _find_source_root,
    check_module_source_path,
)
from src.application.verification.artifact_verifier_types import VerificationResult

# ---------------------------------------------------------------------------
# Fixture content helpers
# ---------------------------------------------------------------------------

_CONTENT_WITH_MODULE = """\
## Description

An entity with a Module property.

## Properties

| Attribute | Value |
|---|---|
| Language | Python |
| Module | src/domain/modules/module_catalog.py |
| Storage | Immutable |
"""

_CONTENT_NO_MODULE = """\
## Description

An entity without a Module property.

## Properties

| Attribute | Value |
|---|---|
| Language | Python |
"""

_CONTENT_NO_PROPERTIES = """\
## Description

An entity with no Properties table at all.
"""


def _result(path: Path) -> VerificationResult:
    return VerificationResult(path=path, file_type="entity")


def _entity_file(base: Path) -> Path:
    """Return a plausible entity file path nested under base."""
    p = base / "model" / "application" / "entity.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# _find_source_root
# ---------------------------------------------------------------------------


def test_find_source_root_returns_ancestor_with_src(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    nested = tmp_path / "engagements" / "repo" / "model" / "entity.md"
    nested.parent.mkdir(parents=True)
    assert _find_source_root(nested) == tmp_path


def test_find_source_root_returns_none_when_no_src(tmp_path: Path) -> None:
    # tmp_path has no src/ child — only bare directories
    nested = tmp_path / "model" / "entity.md"
    nested.parent.mkdir(parents=True)
    # Walk stops at filesystem root; expect None (no src/ ancestor under tmp_path)
    result = _find_source_root(nested)
    # Either None (most likely) or a real system ancestor: we cannot assert None
    # unconditionally, so we only check the case where tmp_path itself has no src/
    if result is not None:
        # Some ancestor above tmp_path has src/; that's fine — skip this assertion
        pytest.skip("Host filesystem has src/ ancestor above tmp_path")


# ---------------------------------------------------------------------------
# check_module_source_path — no Properties table
# ---------------------------------------------------------------------------


def test_no_issues_when_no_properties_table(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    entity = _entity_file(tmp_path)
    r = _result(entity)
    check_module_source_path(_CONTENT_NO_PROPERTIES, entity, r, "loc")
    assert r.issues == []


# ---------------------------------------------------------------------------
# check_module_source_path — Properties table but no Module key
# ---------------------------------------------------------------------------


def test_no_issues_when_no_module_property(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    entity = _entity_file(tmp_path)
    r = _result(entity)
    check_module_source_path(_CONTENT_NO_MODULE, entity, r, "loc")
    assert r.issues == []


# ---------------------------------------------------------------------------
# check_module_source_path — Module key exists, file present
# ---------------------------------------------------------------------------


def test_no_issues_when_module_file_exists(tmp_path: Path) -> None:
    module_file = tmp_path / "src" / "domain" / "modules" / "module_catalog.py"
    module_file.parent.mkdir(parents=True)
    module_file.write_text("# real module")
    entity = _entity_file(tmp_path)
    r = _result(entity)
    check_module_source_path(_CONTENT_WITH_MODULE, entity, r, "loc")
    assert r.issues == []


# ---------------------------------------------------------------------------
# check_module_source_path — Module key exists, file MISSING → W160
# ---------------------------------------------------------------------------


def test_w160_when_module_file_missing(tmp_path: Path) -> None:
    """W160 is reported when the Module property path does not exist."""
    # src/ directory exists but not the specific file
    (tmp_path / "src" / "domain").mkdir(parents=True)
    entity = _entity_file(tmp_path)
    r = _result(entity)
    check_module_source_path(_CONTENT_WITH_MODULE, entity, r, "loc")
    assert len(r.issues) == 1
    issue = r.issues[0]
    assert issue.code == "W160"
    assert issue.severity == "warning"
    assert "src/domain/modules/module_catalog.py" in issue.message


def test_w160_message_contains_the_bad_path(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    content = """\
## Properties

| Attribute | Value |
|---|---|
| Module | src/common/deleted_module.py |
"""
    entity = _entity_file(tmp_path)
    r = _result(entity)
    check_module_source_path(content, entity, r, "loc")
    assert any(i.code == "W160" and "src/common/deleted_module.py" in i.message for i in r.issues)


# ---------------------------------------------------------------------------
# check_module_source_path — no src/ ancestor → silently skips
# ---------------------------------------------------------------------------


def test_no_issues_when_no_source_root(tmp_path: Path) -> None:
    """When no ancestor has src/, the check silently skips (repo not co-located)."""
    # Do NOT create a src/ directory under tmp_path
    # We use an isolated sub-directory where no ancestor contains src/
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    entity2 = isolated / "entity.md"
    r2 = VerificationResult(path=entity2, file_type="entity")
    # Without src/ ancestor, _find_source_root returns None → no issues
    # (unless the host system has a /src directory — extremely unlikely)
    root = _find_source_root(entity2)
    if root is not None:
        pytest.skip("Host filesystem has unexpected src/ ancestor")
    check_module_source_path(_CONTENT_WITH_MODULE, entity2, r2, "loc")
    assert r2.issues == []

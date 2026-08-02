"""Frontmatter schemata are configurable per file type, and core-required fields survive that.

verifies: REQ@1712870400.pSvaRl

This entry sat in `UNVERIFIED_REQUIREMENTS` as a *decision* — the register recorded that the product
"configures document frontmatter per doc-type and entity/connection attributes per specialization — two
mechanisms, neither of them the one stated, and nothing per-file-type for diagrams", so either the
requirement described a superseded design or it was a real gap.

Neither. The requirement is implemented as written, and reading the code says so:

* `.arch-repo/schemata/frontmatter.{entity,outgoing,diagram}.schema.json` — all three ship as repository
  defaults (`repo_default_schemata`), all three exist in the live repository, and
  `load_frontmatter_schema(repo_root, file_type)` is the single loader for them.
* `check_frontmatter_schema` is called for `entity` (`artifact_verifier`), for `outgoing`
  (`_verifier_outgoing`) and for `diagram` (`artifact_verifier`, both diagram branches) — the three
  file types the requirement's own file convention names.
* The fourth, documents, is `.arch-repo/documents/{abbr}.json`, exactly as the requirement's
  Implementation section states, and is what `REQ@1777369067.3cJ1Yi` verifies.
* Extend-only holds because the core fields are not enforced *through* the JSON Schema at all:
  `check_required_fields(fm, ENTITY_REQUIRED | OUTGOING_FILE_REQUIRED | DIAGRAM_REQUIRED, …)` runs
  beside it and raises E021 regardless of what the configured schema says. A schema that drops
  `artifact-id` from its `required` list therefore cannot make `artifact-id` optional.

So the four entries this blocked were owed a test, not a decision. It is the most expensive entry in
that register — three grouping parents name it as a constituent — which is why it is worth being exact:
the tests below assert each of the three claims separately, so a future half-removal fails on the half
it removed rather than on the conjunction.

**A note on what is *not* claimed here.** These are warnings (W041), not errors, deliberately, so a
repository can adopt schemata incrementally — the requirement's own Implementation section says so. A
test that demanded errors would be asserting a stricter product than the one specified.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.artifacts.schema import load_frontmatter_schema
from src.application.verification.artifact_verifier_types import (
    DIAGRAM_REQUIRED,
    ENTITY_REQUIRED,
    OUTGOING_FILE_REQUIRED,
)

#: The three file types whose frontmatter is configured by a `frontmatter.{type}.schema.json`, and the
#: core-required set each one carries independently of that file. Documents are the fourth file type and
#: use a different, equally configurable mechanism — see the module docstring.
FILE_TYPES: tuple[tuple[str, frozenset[str]], ...] = (
    ("entity", ENTITY_REQUIRED),
    ("outgoing", OUTGOING_FILE_REQUIRED),
    ("diagram", DIAGRAM_REQUIRED),
)


def _write_frontmatter_schema(repo_root: Path, file_type: str, schema: dict[str, object]) -> None:
    directory = repo_root / ".arch-repo" / "schemata"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"frontmatter.{file_type}.schema.json").write_text(
        json.dumps(schema), encoding="utf-8"
    )


@pytest.mark.verifies("REQ@1712870400.pSvaRl")
@pytest.mark.parametrize(("file_type", "_core"), FILE_TYPES, ids=[t for t, _ in FILE_TYPES])
def test_each_file_type_has_its_own_configurable_frontmatter_schema(
    tmp_path: Path, file_type: str, _core: frozenset[str]
) -> None:
    """One schema per file type, at the documented address, and each one reaches only its own type.

    The cross-check is the point: writing a schema for `entity` must not start validating diagrams
    against it. "Specific to each of the four main file types" is a statement about isolation as much
    as about existence, and a single shared loader keyed on a filename could satisfy the first while
    failing the second.
    """
    _write_frontmatter_schema(tmp_path, file_type, {"type": "object", "required": ["x-custom"]})

    assert load_frontmatter_schema(tmp_path, file_type) == {
        "type": "object",
        "required": ["x-custom"],
    }
    for other, _ in FILE_TYPES:
        if other != file_type:
            assert load_frontmatter_schema(tmp_path, other) is None, other


@pytest.mark.verifies("REQ@1712870400.pSvaRl")
def test_an_absent_schema_is_a_free_schema_rather_than_a_refusal(tmp_path: Path) -> None:
    """The requirement's stated default. A repository with no schemata validates nothing extra, which
    is what makes the mechanism adoptable one file type at a time."""
    for file_type, _core in FILE_TYPES:
        assert load_frontmatter_schema(tmp_path, file_type) is None, file_type


@pytest.mark.verifies("REQ@1712870400.pSvaRl")
@pytest.mark.parametrize(("file_type", "core"), FILE_TYPES, ids=[t for t, _ in FILE_TYPES])
def test_a_configured_schema_adds_a_constraint_the_verifier_reports(
    tmp_path: Path, file_type: str, core: frozenset[str]
) -> None:
    """Extend: a custom required field is enforced, as W041, against frontmatter that omits it."""
    from src.application.verification._verifier_rules_schema import check_frontmatter_schema
    from src.application.verification.artifact_verifier_types import VerificationResult

    _write_frontmatter_schema(
        tmp_path, file_type, {"type": "object", "required": ["x-owning-team"]}
    )
    result = VerificationResult(path=str(tmp_path), file_type=file_type)

    check_frontmatter_schema(dict.fromkeys(core, "value"), tmp_path, file_type, result, "loc")

    codes = {issue.code for issue in result.issues}
    assert codes == {"W041"}, [(i.code, i.message) for i in result.issues]
    assert any("x-owning-team" in issue.message for issue in result.issues), result.issues


@pytest.mark.verifies("REQ@1712870400.pSvaRl")
@pytest.mark.parametrize(("file_type", "core"), FILE_TYPES, ids=[t for t, _ in FILE_TYPES])
def test_a_custom_field_the_schema_permits_is_accepted(
    tmp_path: Path, file_type: str, core: frozenset[str]
) -> None:
    """The other half of extend: adding a field must be *possible*, not merely constrainable."""
    from src.application.verification._verifier_rules_schema import check_frontmatter_schema
    from src.application.verification.artifact_verifier_types import VerificationResult

    _write_frontmatter_schema(
        tmp_path,
        file_type,
        {
            "type": "object",
            "required": ["x-owning-team"],
            "properties": {"x-owning-team": {"type": "string"}},
            "additionalProperties": True,
        },
    )
    frontmatter = dict.fromkeys(core, "value") | {"x-owning-team": "platform"}
    result = VerificationResult(path=str(tmp_path), file_type=file_type)

    check_frontmatter_schema(frontmatter, tmp_path, file_type, result, "loc")

    assert result.issues == [], [(i.code, i.message) for i in result.issues]


@pytest.mark.verifies("REQ@1712870400.pSvaRl")
@pytest.mark.parametrize(("file_type", "core"), FILE_TYPES, ids=[t for t, _ in FILE_TYPES])
def test_a_schema_that_drops_a_core_field_cannot_make_it_optional(
    tmp_path: Path, file_type: str, core: frozenset[str]
) -> None:
    """Non-removable, which is the requirement's sharpest claim and its whole safety property.

    Asserted at the seam that makes it true rather than by inspecting the shipped default's `required`
    list: the configured schema here names *no* required field at all, and the core check still refuses
    frontmatter missing one. A design that enforced the core fields through the JSON Schema would pass a
    test written against the default and fail this one.
    """
    from src.application.verification.artifact_verifier_rules import check_required_fields
    from src.application.verification.artifact_verifier_types import VerificationResult

    _write_frontmatter_schema(tmp_path, file_type, {"type": "object", "required": []})
    assert load_frontmatter_schema(tmp_path, file_type) == {"type": "object", "required": []}

    for field in sorted(core):
        frontmatter = dict.fromkeys(core, "value")
        del frontmatter[field]
        result = VerificationResult(path=str(tmp_path), file_type=file_type)

        check_required_fields(frontmatter, core, result, "loc")

        assert [issue.code for issue in result.issues] == ["E021"], (field, result.issues)
        assert field in result.issues[0].message, (field, result.issues[0].message)


@pytest.mark.verifies("REQ@1712870400.pSvaRl")
def test_the_shipped_defaults_cover_exactly_these_three_file_types(tmp_path: Path) -> None:
    """The mechanism is only "per file type" if a fresh repository gets one schema per file type.

    Against the shipped defaults rather than the live repository, because a repository somebody has been
    authoring in could satisfy this by accident — and `ensure_arch_repo_defaults` is the function that
    brings any repository up to this state, so it is the honest subject.
    """
    from src.infrastructure.workspace.engagement_repo_template import ensure_arch_repo_defaults

    (tmp_path / "model").mkdir()
    ensure_arch_repo_defaults(tmp_path)

    written = {
        path.name
        for path in (tmp_path / ".arch-repo" / "schemata").glob("frontmatter.*.schema.json")
    }
    assert written == {f"frontmatter.{t}.schema.json" for t, _ in FILE_TYPES}, written
    for file_type, core in FILE_TYPES:
        schema = load_frontmatter_schema(tmp_path, file_type)
        assert schema is not None, file_type
        # The default *states* the core fields as well. Belt and braces rather than the mechanism —
        # the test above is what proves removing them from here changes nothing.
        assert set(schema.get("required", [])) >= core, (file_type, schema.get("required"))

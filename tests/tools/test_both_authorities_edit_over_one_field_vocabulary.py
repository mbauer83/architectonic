"""An entity's editable fields do not depend on which repository it lives in.

The engagement edit and the enterprise (admin) edit are two authorities over the same artifact kind.
They were written twice, and the second copy quietly lost two fields: `admin_edit_entity` had no
`attribute_types` and no `specializations` parameter, and its merge call had `attribute_types` wired
to "keep whatever is there". So an enterprise entity's declared attribute types and its
specializations could be written by promotion — the other authorised path into that repository — and
never afterwards changed by the one that exists to edit them.

**That was accretion, not policy, and the evidence is that nothing anywhere refused it.** No raise,
no comment, no test, no ADR row; `admin_ops`' docstring states the boundary contract in full — which
repository may be written and through which path — and says nothing about a field vocabulary. A
refusal that is never written down is indistinguishable from an omission, which is why the state of
affairs survived.

What this file holds is the standing gate. The two signatures are compared field by field, so a field
added to one authority and not the other fails here rather than being discovered by someone who
needed it.

**`group` is deliberately not in the shared set**, and that is the one real difference. It is not a
field on a record: `edit_entity(group=…)` re-derives the artifact id and the file path, so it is a
relocation, and the admin surface can neither create into a group nor move between them. Measured on
2026-09-01: 941 of 944 engagement entities and 2 of 3 enterprise entities live under
`projects/<group>/model/…`, and the two enterprise ones got there by promotion. That gap is a missing
capability rather than a missing parameter, so it is named here and left for its own change.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from src.infrastructure.write.artifact_write.admin_ops import admin_edit_entity
from src.infrastructure.write.artifact_write.entity_edit import edit_entity

#: Parameters that are about *where* an entity lives rather than what it says. See the docstring.
_RELOCATION = frozenset({"group"})

#: Parameters every write takes: the repository, the machinery to verify against, and the subject.
_PLUMBING = frozenset({
    "repo_root", "registry", "verifier", "clear_repo_caches", "artifact_id", "dry_run",
})


@pytest.fixture()
def enterprise_root(tmp_path: Path) -> Path:
    """The same shape `test_admin_mode` builds — an enterprise root the boundary guard accepts."""
    root = tmp_path / "enterprise-repository"
    (root / "model").mkdir(parents=True)
    return root


def _fields(function: object) -> frozenset[str]:
    return frozenset(inspect.signature(function).parameters) - _PLUMBING  # type: ignore[arg-type]


def test_the_two_authorities_accept_the_same_editable_fields() -> None:
    engagement = _fields(edit_entity) - _RELOCATION
    enterprise = _fields(admin_edit_entity) - _RELOCATION
    assert engagement == enterprise, (
        "the two entity edit authorities disagree about which fields are editable:\n"
        f"  only the engagement edit takes: {sorted(engagement - enterprise)}\n"
        f"  only the enterprise edit takes: {sorted(enterprise - engagement)}\n"
        "A field one authority accepts and the other silently ignores is not a policy until "
        "something states it — add it to both, or write the refusal down and name it here."
    )


def test_neither_authority_has_quietly_taken_on_relocation() -> None:
    """The one stated difference, pinned so it stays stated.

    If the admin edit ever gains `group`, this file's account of why it does not is out of date and
    should be rewritten rather than left describing a repository that has moved on.
    """
    assert _RELOCATION <= _fields(edit_entity)
    assert _RELOCATION.isdisjoint(_fields(admin_edit_entity))


class TestAnEnterpriseEntityCanHaveItsAttributeTypesChanged:
    """The regression, over the write path rather than the signature.

    `properties` and `attribute_types` are patched key by key, so this asserts the change lands and
    the untouched neighbour survives — the shape a patch has to have to be worth calling one.
    """

    def _edit(self, enterprise_root: Path, **fields: object) -> object:
        from src.application.verification.artifact_verifier import ArtifactVerifier
        from src.application.verification.artifact_verifier_registry import ArtifactRegistry
        from src.infrastructure.artifact_index import shared_artifact_index

        from tests.tools.test_admin_mode import _catalogs, _entity_md, _write

        full = "REQ@1786120500.FieldVo1.an-enterprise-requirement"
        path = enterprise_root / "model" / "motivation" / "requirement" / f"{full}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        _write(path, _entity_md(full, "requirement", "An Enterprise Requirement"))
        registry = ArtifactRegistry(shared_artifact_index([enterprise_root]))
        verifier = ArtifactVerifier(registry, catalogs=_catalogs())
        return admin_edit_entity(
            repo_root=enterprise_root, registry=registry, verifier=verifier,
            clear_repo_caches=lambda _: None, artifact_id=full, dry_run=False, **fields,
        )

    def test_an_attribute_type_reaches_the_file(self, enterprise_root: Path) -> None:
        result = self._edit(
            enterprise_root,
            properties={"Priority": "Must", "Owner": "Platform"},
            attribute_types={"Priority": "string"},
        )

        assert result.wrote, result.verification
        written = Path(result.path).read_text(encoding="utf-8")
        assert "Priority" in written and "string" in written
        assert "Owner" in written, "patching one attribute type dropped an untouched property"

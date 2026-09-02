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

from src.application.modeling import edit_field_catalogue as catalogue
from src.infrastructure.mcp.artifact_mcp.bulk.common import KNOWN_ITEM_FIELDS
from src.infrastructure.write.artifact_write.admin_ops import admin_edit_entity
from src.infrastructure.write.artifact_write.connection_edit import edit_connection
from src.infrastructure.write.artifact_write.entity_edit import edit_entity

#: Parameters that are about *where* an entity lives rather than what it says. See the docstring.
_RELOCATION = frozenset({"group"})

#: Parameters every write takes whatever it is writing: the repository, the machinery to verify
#: against, and whether to commit. Deliberately not `artifact_id` — that addresses the subject, which
#: is part of the vocabulary and is where `edit_field_catalogue` puts it.
_PLUMBING = frozenset({"repo_root", "registry", "verifier", "clear_repo_caches", "dry_run"})


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


class TestTheCatalogueIsTheOneSpellingOfTheVocabulary:
    """`edit_field_catalogue` and the write functions describe the same fields.

    The catalogue exists because this vocabulary was written down three times — the signatures, the
    REST bodies and the MCP bulk decoder — with no way to disagree out loud. Making the decoder a
    projection removes one spelling; this is what stops the remaining two drifting apart, in either
    direction, which is the direction the last drift went.
    """

    def test_the_entity_row_matches_the_write_function(self) -> None:
        assert catalogue.editable("entity") == _fields(edit_entity)

    def test_the_connection_row_matches_the_write_function(self) -> None:
        assert catalogue.editable("connection") == _fields(edit_connection)

    @pytest.mark.parametrize(
        ("kind", "writer"),
        [("document", "edit_document"), ("diagram", "edit_diagram")],
    )
    def test_every_other_kind_matches_its_write_function_too(self, kind: str, writer: str) -> None:
        """The two kinds a proposal can also address. `accepted` rather than `editable`, because a
        diagram's write function takes mechanics — `rebuild_layout`, `replace_bindings`, the
        committed repository — that tell an applier how to behave rather than what the artifact
        should say. The catalogue keeps them apart, and a proposal records only the second kind.
        """
        import importlib

        module = {
            "document": "src.infrastructure.write.artifact_write.document",
            "diagram": "src.infrastructure.write.artifact_write.diagram_edit",
        }[kind]
        function = getattr(importlib.import_module(module), writer)
        assert catalogue.accepted(kind) == _fields(function) - {"assert_write_root"}  # type: ignore[arg-type]

    def test_mechanics_are_never_proposable(self) -> None:
        """A proposal says what the artifact should say; how a replay applies it is the replay's."""
        for kind in catalogue.PROPOSABLE:
            assert catalogue.MECHANICS[kind].isdisjoint(catalogue.editable(kind))

    def test_the_decoder_projects_the_catalogue_rather_than_restating_it(self) -> None:
        """The envelope is the decoder's own; everything else it accepts comes from the catalogue."""
        envelope = frozenset({"op", "_ref"})
        assert KNOWN_ITEM_FIELDS["edit_entity"] == envelope | catalogue.editable("entity")
        assert KNOWN_ITEM_FIELDS["edit_connection"] - {"operation"} == (
            envelope | catalogue.editable("connection")
        )

    def test_the_envelope_is_not_in_the_catalogue(self) -> None:
        """`op` and `_ref` are properties of a batch request, and no write function has heard of them.

        Keeping them out is what makes the two assertions above checkable at all.
        """
        for kind in ("entity", "connection"):
            assert {"op", "_ref"}.isdisjoint(catalogue.editable(kind))  # type: ignore[arg-type]


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

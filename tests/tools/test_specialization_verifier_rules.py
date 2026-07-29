"""Unit tests for the specialization verifier rules: unknown-slug and wrong-type errors
(E160/E161 for connections, E170/E171 for entities), and the endpoint/relationship
restriction warnings (W128/W129). All four checked functions are pure (catalog + already-
resolved strings in, `Issue`s appended to a `VerificationResult`), so no registry or
filesystem fixture is needed.
"""

from __future__ import annotations

from pathlib import Path

from src.application.verification._verifier_outgoing import _check_connection_specialization
from src.application.verification._verifier_rules_semantic import (
    _check_connection_endpoint_restriction,
    _check_entity_relationship_restriction,
)
from src.application.verification._verifier_rules_specialization import check_entity_specialization
from src.application.verification.artifact_verifier_types import VerificationResult
from src.domain.ontology_representation.specializations import (
    EndpointRestriction,
    RelationshipRestriction,
    SpecializationCatalog,
    SpecializationInfo,
)

_CATALOG = SpecializationCatalog(
    (
        SpecializationInfo(
            slug="business-collaboration",
            name="Business Collaboration",
            concept_kind="entity",
            parent_type="collaboration",
            module_alias="archimate-4",
            restrict_relationships=(
                RelationshipRestriction(connection_type="archimate-assignment", target_type="requirement"),
            ),
        ),
        SpecializationInfo(
            slug="unrestricted-role",
            name="Unrestricted Role",
            concept_kind="entity",
            parent_type="role",
            module_alias="archimate-4",
        ),
        SpecializationInfo(
            slug="responsibility-assignment",
            name="Responsibility Assignment",
            concept_kind="connection",
            parent_type="archimate-assignment",
            module_alias="archimate-4",
            restrict_endpoints=(
                EndpointRestriction(source_types=frozenset({"grouping"}), target_types=frozenset({"requirement"})),
            ),
        ),
        SpecializationInfo(
            slug="unrestricted-assignment",
            name="Unrestricted Assignment",
            concept_kind="connection",
            parent_type="archimate-assignment",
            module_alias="archimate-4",
        ),
    )
)

_LOC = str(Path("dummy.md"))


def _codes(result: VerificationResult) -> list[str]:
    return [i.code for i in result.issues]


class TestConnectionSpecializationSlug:
    def test_unknown_slug_is_e160(self) -> None:
        result = VerificationResult(path=Path(_LOC), file_type="connection")
        _check_connection_specialization("does-not-exist", "archimate-assignment", _CATALOG, result, _LOC)
        assert _codes(result) == ["E160"]

    def test_slug_declared_for_different_kind_is_e161(self) -> None:
        # "business-collaboration" is an entity-kind slug, not a connection-kind one.
        result = VerificationResult(path=Path(_LOC), file_type="connection")
        _check_connection_specialization("business-collaboration", "archimate-assignment", _CATALOG, result, _LOC)
        assert _codes(result) == ["E161"]

    def test_valid_slug_for_type_is_silent(self) -> None:
        result = VerificationResult(path=Path(_LOC), file_type="connection")
        _check_connection_specialization("responsibility-assignment", "archimate-assignment", _CATALOG, result, _LOC)
        assert result.issues == []


class TestEntitySpecializationSlug:
    def test_unknown_slug_is_e170(self) -> None:
        result = VerificationResult(path=Path(_LOC), file_type="entity")
        check_entity_specialization(
            {"specialization": "does-not-exist", "artifact-type": "collaboration"}, _CATALOG, result, _LOC
        )
        assert _codes(result) == ["E170"]

    def test_slug_declared_for_different_type_is_e171(self) -> None:
        # "responsibility-assignment" is a connection-kind slug, not declared for entities.
        result = VerificationResult(path=Path(_LOC), file_type="entity")
        check_entity_specialization(
            {"specialization": "responsibility-assignment", "artifact-type": "collaboration"}, _CATALOG, result, _LOC
        )
        assert _codes(result) == ["E171"]

    def test_valid_slug_for_type_is_silent(self) -> None:
        result = VerificationResult(path=Path(_LOC), file_type="entity")
        check_entity_specialization(
            {"specialization": "business-collaboration", "artifact-type": "collaboration"}, _CATALOG, result, _LOC
        )
        assert result.issues == []

    def test_absent_specialization_field_is_silent(self) -> None:
        result = VerificationResult(path=Path(_LOC), file_type="entity")
        check_entity_specialization({"artifact-type": "collaboration"}, _CATALOG, result, _LOC)
        assert result.issues == []


class TestConnectionEndpointRestriction:
    def test_disallowed_pair_is_w128(self) -> None:
        result = VerificationResult(path=Path(_LOC), file_type="connection")
        _check_connection_endpoint_restriction(
            _CATALOG,
            slug="responsibility-assignment",
            conn_type="archimate-assignment",
            source_type="capability",
            target_type="requirement",
            result=result,
            loc=_LOC,
        )
        assert _codes(result) == ["W128"]

    def test_allowed_pair_is_silent(self) -> None:
        result = VerificationResult(path=Path(_LOC), file_type="connection")
        _check_connection_endpoint_restriction(
            _CATALOG,
            slug="responsibility-assignment",
            conn_type="archimate-assignment",
            source_type="grouping",
            target_type="requirement",
            result=result,
            loc=_LOC,
        )
        assert result.issues == []

    def test_slug_without_restrict_endpoints_is_silent(self) -> None:
        result = VerificationResult(path=Path(_LOC), file_type="connection")
        _check_connection_endpoint_restriction(
            _CATALOG, slug="unrestricted-assignment", conn_type="archimate-assignment",
            source_type="capability", target_type="requirement", result=result, loc=_LOC,
        )
        assert result.issues == []


class TestEntityRelationshipRestriction:
    def test_disallowed_triple_is_w129(self) -> None:
        result = VerificationResult(path=Path(_LOC), file_type="connection")
        _check_entity_relationship_restriction(
            _CATALOG,
            entity_id="COL@1.A.src",
            entity_type="collaboration",
            slug="business-collaboration",
            conn_type="archimate-assignment",
            source_type="collaboration",
            target_type="capability",
            role="source",
            result=result,
            loc=_LOC,
        )
        assert _codes(result) == ["W129"]

    def test_allowed_triple_is_silent(self) -> None:
        result = VerificationResult(path=Path(_LOC), file_type="connection")
        _check_entity_relationship_restriction(
            _CATALOG,
            entity_id="COL@1.A.src",
            entity_type="collaboration",
            slug="business-collaboration",
            conn_type="archimate-assignment",
            source_type="collaboration",
            target_type="requirement",
            role="source",
            result=result,
            loc=_LOC,
        )
        assert result.issues == []

    def test_slug_without_restrict_relationships_is_silent(self) -> None:
        result = VerificationResult(path=Path(_LOC), file_type="connection")
        _check_entity_relationship_restriction(
            _CATALOG,
            entity_id="ROL@1.A.role",
            entity_type="role",
            slug="unrestricted-role",
            conn_type="archimate-assignment",
            source_type="role",
            target_type="anything-at-all",
            role="source",
            result=result,
            loc=_LOC,
        )
        assert result.issues == []

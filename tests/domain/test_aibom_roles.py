"""WU-A3: the AIBOM derivation-role vocabulary, its shipped defaults, and the repo override
merge — the roles are closed, the bindings are open (PLAN §5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.aibom.role_loading import resolve_aibom_role_bindings
from src.domain.assurance.aibom_roles import (
    AIBOM_DERIVATION_ROLES,
    DerivationRoleError,
    merge_role_bindings,
    role_bindings_from_mapping,
)
from src.ontologies.archimate_4._yaml_data import load_module_aibom_roles

_PACKAGE_DIR = Path("src/ontologies/archimate_4")


class TestShippedDefaults:
    def test_every_vocabulary_role_ships_a_binding(self) -> None:
        bindings = load_module_aibom_roles(_PACKAGE_DIR)
        assert bindings.bound_roles() == AIBOM_DERIVATION_ROLES
        assert bindings.unbound_roles() == frozenset()

    def test_a_binding_names_connection_types_and_target_specs(self) -> None:
        bindings = load_module_aibom_roles(_PACKAGE_DIR)
        trained = bindings.get("trained-on")
        assert trained is not None
        assert "archimate-access" in trained.connection_types
        assert trained.target_specializations == ("ai-dataset",)


class TestParsing:
    def test_unknown_role_name_is_a_typed_error(self) -> None:
        with pytest.raises(DerivationRoleError, match="unknown derivation role"):
            role_bindings_from_mapping(
                {"roles": {"not-a-role": {"connection_types": ["archimate-access"]}}}, label="test"
            )

    def test_a_binding_with_no_connection_type_is_an_error(self) -> None:
        with pytest.raises(DerivationRoleError, match="at least one connection_type"):
            role_bindings_from_mapping({"roles": {"trained-on": {"connection_types": []}}}, label="test")

    def test_non_mapping_top_level_is_an_error(self) -> None:
        with pytest.raises(DerivationRoleError):
            role_bindings_from_mapping([1, 2, 3], label="test")


class TestMerge:
    def test_override_replaces_exactly_the_named_role(self) -> None:
        base = load_module_aibom_roles(_PACKAGE_DIR)
        override = role_bindings_from_mapping(
            {"roles": {"served-by": {"connection_types": ["archimate-realization"], "target_specializations": []}}},
            label="override",
        )
        merged = merge_role_bindings(base, override)
        # the overridden role took the new binding …
        assert merged.get("served-by").connection_types == ("archimate-realization",)
        # … and every other role is untouched.
        assert merged.get("trained-on").connection_types == base.get("trained-on").connection_types
        assert merged.bound_roles() == base.bound_roles()


class TestRepoOverrideLoading:
    def test_absent_repo_file_returns_shipped_unchanged(self, tmp_path: Path) -> None:
        shipped = load_module_aibom_roles(_PACKAGE_DIR)
        resolved = resolve_aibom_role_bindings(tmp_path, shipped)
        assert resolved.get("served-by").connection_types == shipped.get("served-by").connection_types

    def test_present_repo_file_overrides_one_role(self, tmp_path: Path) -> None:
        (tmp_path / ".arch-repo").mkdir()
        (tmp_path / ".arch-repo" / "aibom-roles.yaml").write_text(
            "roles:\n"
            "  trained-on:\n"
            "    connection_types: [archimate-realization]\n"
            "    target_specializations: [ai-dataset]\n",
            encoding="utf-8",
        )
        shipped = load_module_aibom_roles(_PACKAGE_DIR)
        resolved = resolve_aibom_role_bindings(tmp_path, shipped)
        assert resolved.get("trained-on").connection_types == ("archimate-realization",)
        assert resolved.get("evaluated-on").connection_types == shipped.get("evaluated-on").connection_types

    def test_unknown_role_in_repo_override_is_a_typed_error(self, tmp_path: Path) -> None:
        (tmp_path / ".arch-repo").mkdir()
        (tmp_path / ".arch-repo" / "aibom-roles.yaml").write_text(
            "roles:\n  bogus-role:\n    connection_types: [archimate-access]\n", encoding="utf-8"
        )
        with pytest.raises(DerivationRoleError, match="unknown derivation role"):
            resolve_aibom_role_bindings(tmp_path, load_module_aibom_roles(_PACKAGE_DIR))

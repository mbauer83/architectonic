"""The two-stage deployment-layout resolver: selector permutations + conflicts."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.deployment.layout import (
    ENV_ASSURANCE_DB_PATH,
    ENV_SETTINGS_PATH,
    CliSelectors,
    DeploymentLayoutConflict,
    SettingsValues,
)
from src.domain.deployment.layout_resolution import (
    LayoutInputs,
    resolve_deployment_layout,
    select_settings_document,
)

_TREE = Path("/opt/product")
_HOME = Path("/home/op")
_CWD = Path("/home/op/work")


def _inputs(
    *,
    cli: CliSelectors = CliSelectors(),
    env: dict[str, str] | None = None,
    settings: SettingsValues = SettingsValues(),
    deployment_root: Path | None = None,
    settings_dir: Path = _TREE / "config",
) -> LayoutInputs:
    return LayoutInputs(
        cli=cli,
        env=env or {},
        settings=settings,
        settings_dir=settings_dir,
        deployment_root=deployment_root,
        source_tree_root=_TREE,
        home=_HOME,
        cwd=_CWD,
    )


def _selection(**kwargs):  # type: ignore[no-untyped-def]
    defaults = dict(
        cli_settings=None,
        deployment_root=None,
        env={},
        source_tree_settings=_TREE / "config" / "settings.yaml",
        cwd=_CWD,
    )
    return select_settings_document(**{**defaults, **kwargs})


class TestStageOneSelection:
    def test_cli_settings_wins_over_everything(self) -> None:
        selection = _selection(
            cli_settings="my/settings.yaml",
            deployment_root=Path("/deploy"),
            env={ENV_SETTINGS_PATH: "/env/settings.yaml"},
        )
        assert selection.path == _CWD / "my" / "settings.yaml"
        assert selection.source == "cli"
        assert selection.operator_owned

    def test_deployment_root_default_beats_env(self) -> None:
        selection = _selection(
            deployment_root=Path("/deploy"), env={ENV_SETTINGS_PATH: "/env/settings.yaml"}
        )
        assert selection.path == Path("/deploy/settings.yaml")
        assert selection.source == "deployment_root_default"

    def test_env_selector_beats_source_tree_fallback(self) -> None:
        selection = _selection(env={ENV_SETTINGS_PATH: "/env/settings.yaml"})
        assert selection.path == Path("/env/settings.yaml")
        assert selection.source == "env"
        assert selection.operator_owned

    def test_source_tree_fallback_is_not_operator_owned(self) -> None:
        selection = _selection()
        assert selection.path == _TREE / "config" / "settings.yaml"
        assert selection.source == "source_tree_default"
        assert not selection.operator_owned


# One row per (field, source-combination) — the normative source-table permutations.
_FIELD_CASES = [
    # (field, cli kwargs, settings kwargs, env, expected path, expected source)
    ("assurance_db_path", {"assurance_store": "/x/store.db"}, {}, {}, "/x/store.db", "cli"),
    ("assurance_db_path", {}, {"deployment_assurance_db_path": "/s/store.db"}, {}, "/s/store.db", "settings"),
    ("assurance_db_path", {}, {}, {ENV_ASSURANCE_DB_PATH: "/e/store.db"}, "/e/store.db", "env"),
    ("signals_db_path", {"signals_db": "/x/sig.db"}, {}, {}, "/x/sig.db", "cli"),
    ("signals_db_path", {}, {"deployment_signals_db_path": "/s/sig.db"}, {}, "/s/sig.db", "settings"),
    ("signals_db_path", {}, {}, {"ARCH_SECURITY_SIGNALS_DB_PATH": "/e/sig.db"}, "/e/sig.db", "env"),
    ("guidance_cache_root", {"guidance_cache": "/x/cache"}, {}, {}, "/x/cache", "cli"),
    ("guidance_cache_root", {}, {"deployment_guidance_cache_root": "/s/cache"}, {}, "/s/cache", "settings"),
    ("workspace_root", {"workspace": "/x/ws"}, {}, {}, "/x/ws", "cli"),
    ("workspace_root", {}, {"deployment_workspace_root": "/s/ws"}, {}, "/s/ws", "settings"),
]


class TestStageTwoSources:
    @pytest.mark.parametrize(("field", "cli", "settings", "env", "expected", "source"), _FIELD_CASES)
    def test_each_explicit_source_resolves_and_is_attributed(
        self, field: str, cli: dict, settings: dict, env: dict, expected: str, source: str
    ) -> None:
        inputs = _inputs(cli=CliSelectors(**cli), settings=SettingsValues(**settings), env=env)
        manifest = resolve_deployment_layout(inputs, _selection())
        resolved = getattr(manifest, field)
        assert resolved.path == Path(expected)
        assert resolved.source == source

    def test_settings_relative_paths_resolve_against_the_settings_dir(self) -> None:
        inputs = _inputs(
            settings=SettingsValues(deployment_assurance_db_path="stores/a.db"),
            settings_dir=Path("/deploy/conf"),
        )
        manifest = resolve_deployment_layout(inputs, _selection())
        assert manifest.assurance_db_path.path == Path("/deploy/conf/stores/a.db")

    def test_compat_defaults_without_any_selector(self) -> None:
        manifest = resolve_deployment_layout(_inputs(), _selection())
        assert manifest.assurance_db_path.path == _TREE / ".arch-assurance" / "store.db"
        assert manifest.signals_db_path.path == _TREE / ".arch-assurance" / "security-signals.db"
        assert manifest.guidance_cache_root.path == _HOME / ".config" / "arch-repo" / "guidance-cache"
        assert manifest.workspace_root is None  # callers keep CWD/arch-init behavior
        assert manifest.assurance_db_path.source == "compat_default"

    def test_deployment_root_defaults_apply_only_with_a_deployment_root(self) -> None:
        root = Path("/deploy")
        manifest = resolve_deployment_layout(_inputs(deployment_root=root), _selection())
        assert manifest.assurance_db_path.path == root / ".arch-assurance" / "store.db"
        assert manifest.signals_db_path.path == root / ".arch-assurance" / "security-signals.db"
        assert manifest.guidance_cache_root.path == root / "guidance-cache"
        assert manifest.workspace_root is not None
        assert manifest.workspace_root.path == root / "workspace"
        assert manifest.assurance_db_path.source == "deployment_root_default"


class TestConflicts:
    @pytest.mark.parametrize(
        ("cli", "settings", "env"),
        [
            ({"assurance_store": "/a.db"}, {"deployment_assurance_db_path": "/b.db"}, {}),
            ({"assurance_store": "/a.db"}, {}, {ENV_ASSURANCE_DB_PATH: "/b.db"}),
            ({}, {"deployment_assurance_db_path": "/a.db"}, {ENV_ASSURANCE_DB_PATH: "/b.db"}),
        ],
    )
    def test_two_explicit_selectors_with_different_values_error(
        self, cli: dict, settings: dict, env: dict
    ) -> None:
        inputs = _inputs(cli=CliSelectors(**cli), settings=SettingsValues(**settings), env=env)
        with pytest.raises(DeploymentLayoutConflict) as excinfo:
            resolve_deployment_layout(inputs, _selection())
        assert excinfo.value.field_name == "assurance_db_path"

    def test_equal_values_from_multiple_sources_merge_provenance(self) -> None:
        inputs = _inputs(
            cli=CliSelectors(assurance_store="/same/store.db"),
            settings=SettingsValues(deployment_assurance_db_path="/same/store.db"),
            env={ENV_ASSURANCE_DB_PATH: "/same/store.db"},
        )
        manifest = resolve_deployment_layout(inputs, _selection())
        assert manifest.assurance_db_path.path == Path("/same/store.db")
        assert manifest.assurance_db_path.source == "cli"
        assert [p.source for p in manifest.assurance_db_path.provenance] == ["cli", "settings", "env"]

    def test_a_default_never_conflicts_with_an_explicit_value(self) -> None:
        inputs = _inputs(
            cli=CliSelectors(assurance_store="/explicit/store.db"), deployment_root=Path("/deploy")
        )
        manifest = resolve_deployment_layout(inputs, _selection())
        assert manifest.assurance_db_path.path == Path("/explicit/store.db")


class TestArchiveIdentity:
    def test_local_archives_derive_from_the_assurance_db_itself(self) -> None:
        manifest = resolve_deployment_layout(
            _inputs(settings=SettingsValues(archive_backend="worm")), _selection()
        )
        assert manifest.archive_identity is None
        assert manifest.archive_notes == ()

    def test_s3_identity_tuple_is_bucket_plus_prefix(self) -> None:
        settings = SettingsValues(
            archive_backend="s3-worm", archive={"s3_bucket": "b", "s3_prefix": "ns-1/"}
        )
        manifest = resolve_deployment_layout(_inputs(settings=settings), _selection())
        assert manifest.archive_identity is not None
        assert manifest.archive_identity.identity == ("b", "ns-1/")
        assert manifest.archive_identity.source == "settings"

    def test_s3_settings_override_env_without_conflict(self) -> None:
        settings = SettingsValues(archive_backend="s3-worm", archive={"s3_bucket": "from-settings"})
        manifest = resolve_deployment_layout(
            _inputs(settings=settings, env={"ARCH_S3_BUCKET": "from-env"}), _selection()
        )
        assert manifest.archive_identity is not None
        assert manifest.archive_identity.identity[0] == "from-settings"

    def test_azure_state_container_participates_in_identity(self) -> None:
        settings = SettingsValues(
            archive_backend="azure-blob-worm",
            archive={
                "azure_storage_account": "acct",
                "azure_container": "arch",
                "azure_state_container": "state",
            },
        )
        manifest = resolve_deployment_layout(_inputs(settings=settings), _selection())
        assert manifest.archive_identity is not None
        assert manifest.archive_identity.identity == ("acct", "arch", "state")

    def test_incomplete_cloud_identity_is_a_preflight_note_never_a_crash(self) -> None:
        manifest = resolve_deployment_layout(
            _inputs(settings=SettingsValues(archive_backend="s3-worm")), _selection()
        )
        assert manifest.archive_identity is None
        assert any("s3-worm" in note for note in manifest.archive_notes)

    def test_secrets_never_appear_in_reportable_fields(self) -> None:
        settings = SettingsValues(archive_backend="s3-worm", archive={"s3_bucket": "b"})
        manifest = resolve_deployment_layout(
            _inputs(settings=settings, env={"AWS_SECRET_ACCESS_KEY": "sekret"}), _selection()
        )
        assert manifest.archive_identity is not None
        assert "sekret" not in str(manifest.archive_identity.reportable)


class TestWorkspaceIsolation:
    def test_two_deployment_roots_never_share_operational_paths(self) -> None:
        first = resolve_deployment_layout(_inputs(deployment_root=Path("/deploy/a")), _selection())
        second = resolve_deployment_layout(_inputs(deployment_root=Path("/deploy/b")), _selection())
        assert first.assurance_db_path.path != second.assurance_db_path.path
        assert first.signals_db_path.path != second.signals_db_path.path
        assert first.guidance_cache_root.path != second.guidance_cache_root.path

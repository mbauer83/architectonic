"""The impure layout shell: settings parsing, canonical manifests, and the
Docker/runtime handoff (byte-identical canonical paths from one identity)."""

from __future__ import annotations

from pathlib import Path

from src.domain.deployment.layout import ENV_SETTINGS_PATH, CliSelectors
from src.infrastructure.deployment.layout import (
    load_settings_values,
    resolve_manifest,
    resolve_settings_selection,
)


class TestSettingsValueParsing:
    def test_absent_document_yields_defaults(self, tmp_path: Path) -> None:
        values = load_settings_values(tmp_path / "missing.yaml")
        assert values.store_backend == "sqlcipher"
        assert values.signals_backend == "sqlcipher-colocated"
        assert values.assurance_enabled

    def test_deployment_section_and_backends_are_read(self, tmp_path: Path) -> None:
        doc = tmp_path / "settings.yaml"
        doc.write_text(
            "deployment:\n"
            "  workspace_root: ws\n"
            "  assurance_db_path: stores/a.db\n"
            "  guidance_cache_root: cache\n"
            "  archive:\n"
            "    s3_bucket: bkt\n"
            "storage:\n"
            "  assurance:\n"
            "    signals_backend: sqlite\n"
            "    archive_backend: s3-worm\n"
            "modules:\n"
            "  assurance:\n"
            "    enabled: false\n",
            encoding="utf-8",
        )
        values = load_settings_values(doc)
        assert values.deployment_workspace_root == "ws"
        assert values.deployment_assurance_db_path == "stores/a.db"
        assert values.deployment_guidance_cache_root == "cache"
        assert values.signals_backend == "sqlite"
        assert values.archive_backend == "s3-worm"
        assert not values.assurance_enabled
        assert values.archive["s3_bucket"] == "bkt"


class TestManifestResolution:
    def test_deployment_root_manifest_resolves_settings_relative_paths(self, tmp_path: Path) -> None:
        root = tmp_path / "deploy"
        root.mkdir()
        (root / "settings.yaml").write_text(
            "deployment:\n  assurance_db_path: stores/a.db\n", encoding="utf-8"
        )
        manifest = resolve_manifest(CliSelectors(deployment_root=str(root)), env={})
        assert manifest.settings_document.path == (root / "settings.yaml").resolve()
        assert manifest.assurance_db_path.path == (root / "stores" / "a.db").resolve()
        assert manifest.guidance_cache_root.path == (root / "guidance-cache").resolve()

    def test_docker_env_and_cli_settings_produce_byte_identical_manifests(
        self, tmp_path: Path
    ) -> None:
        """Docker exports ARCH_SETTINGS_PATH for runtime and passes --settings to the
        upgrade CLI — both must open the exact same canonical paths."""
        doc = tmp_path / "settings.yaml"
        doc.write_text("deployment:\n  assurance_db_path: stores/a.db\n", encoding="utf-8")
        via_cli = resolve_manifest(CliSelectors(settings=str(doc)), env={})
        via_env = resolve_manifest(CliSelectors(), env={ENV_SETTINGS_PATH: str(doc)})
        assert str(via_cli.assurance_db_path.path) == str(via_env.assurance_db_path.path)
        assert str(via_cli.signals_db_path.path) == str(via_env.signals_db_path.path)
        assert str(via_cli.guidance_cache_root.path) == str(via_env.guidance_cache_root.path)
        assert via_cli.settings_document.path == via_env.settings_document.path

    def test_symlinked_locations_canonicalize_to_one_physical_identity(self, tmp_path: Path) -> None:
        real = tmp_path / "real"
        real.mkdir()
        (real / "settings.yaml").write_text("{}\n", encoding="utf-8")
        link = tmp_path / "link"
        link.symlink_to(real, target_is_directory=True)
        via_real = resolve_manifest(CliSelectors(deployment_root=str(real)), env={})
        via_link = resolve_manifest(CliSelectors(deployment_root=str(link)), env={})
        assert via_real.assurance_db_path.path == via_link.assurance_db_path.path

    def test_two_workspaces_under_one_home_stay_isolated(self, tmp_path: Path) -> None:
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        manifest_a = resolve_manifest(CliSelectors(deployment_root=str(a)), env={})
        manifest_b = resolve_manifest(CliSelectors(deployment_root=str(b)), env={})
        paths_a = {
            str(manifest_a.assurance_db_path.path),
            str(manifest_a.signals_db_path.path),
            str(manifest_a.guidance_cache_root.path),
        }
        paths_b = {
            str(manifest_b.assurance_db_path.path),
            str(manifest_b.signals_db_path.path),
            str(manifest_b.guidance_cache_root.path),
        }
        assert paths_a.isdisjoint(paths_b)


class TestStageOneShell:
    def test_source_tree_fallback_without_any_identity(self) -> None:
        selection = resolve_settings_selection(CliSelectors(), env={})
        assert selection.source == "source_tree_default"
        assert not selection.operator_owned
        assert selection.path.name == "settings.yaml"

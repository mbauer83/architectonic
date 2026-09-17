"""A group or extra is selected exactly when every distribution it names is installed."""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.software_update.uv_environment import derive_selection

PYPROJECT = '''
[project]
name = "x"
version = "0.1.0"
dependencies = ["pyyaml>=6"]

[project.optional-dependencies]
s3-archive = ["boto3>=1.34"]
azure-archive = ["azure-storage-blob>=12.19", "azure-identity>=1.15"]
cloud-archive = ["boto3>=1.34", "azure-storage-blob>=12.19", "azure-identity>=1.15"]

[dependency-groups]
dev = ["pytest>=8.3", "moto[s3]>=5.0", "boto3>=1.34"]
gui = ["fastapi>=0.115.0", "uvicorn[standard]>=0.32.0"]
'''


def _selection(tmp_path: Path, installed: set[str]):  # noqa: ANN202
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    return derive_selection(tmp_path / "pyproject.toml", installed=lambda name: name in installed)


def test_a_full_developer_environment_selects_dev_gui_and_the_extras_dev_subsumes(tmp_path: Path) -> None:
    selection = _selection(tmp_path, {"pytest", "moto", "boto3", "fastapi", "uvicorn"})

    assert selection.groups == ("dev", "gui")
    # `s3-archive` names only boto3, which dev brought; naming it changes nothing about the result.
    assert selection.extras == ("s3-archive",)
    assert selection.sync_arguments() == ("--frozen", "--group", "dev", "--group", "gui", "--extra", "s3-archive")


def test_a_runtime_only_environment_selects_just_gui(tmp_path: Path) -> None:
    assert _selection(tmp_path, {"fastapi", "uvicorn"}) .groups == ("gui",)
    assert _selection(tmp_path, {"fastapi", "uvicorn"}).extras == ()


def test_a_partially_installed_group_is_not_selected(tmp_path: Path) -> None:
    assert _selection(tmp_path, {"fastapi"}).groups == ()


def test_extras_and_markers_in_a_requirement_do_not_hide_its_name(tmp_path: Path) -> None:
    selection = _selection(tmp_path, {"boto3", "azure-storage-blob", "azure-identity"})
    assert selection.extras == ("s3-archive", "azure-archive", "cloud-archive")

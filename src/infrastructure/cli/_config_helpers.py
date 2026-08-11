"""Config-write helpers for arch-assurance CLI commands."""

from __future__ import annotations

from pathlib import Path

from src.domain.yaml_documents import parse_yaml


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[3]


def write_storage_config(
    store_backend: str,
    signals_backend: str,
    archive_backend: str | None = None,
    activation_policy: str | None = None,
) -> None:
    """Write storage.assurance settings to the active settings document
    (honors `ARCH_SETTINGS_PATH`; falls back to config/settings.yaml).

    archive_backend and activation_policy are only written when explicitly supplied so that callers
    that don't set them leave existing config untouched.
    """
    import copy  # noqa: PLC0415

    import yaml  # noqa: PLC0415

    from src.config.settings import settings_document_path  # noqa: PLC0415

    config_path = settings_document_path()
    data: dict[str, object]
    if config_path.exists():
        data = parse_yaml(config_path.read_text(encoding="utf-8")) or {}
    else:
        data = {}
    before = copy.deepcopy(data)
    storage: dict[str, object] = data.setdefault("storage", {})  # type: ignore[assignment]
    assurance: dict[str, object] = storage.setdefault("assurance", {})  # type: ignore[assignment]
    assurance["store_backend"] = store_backend
    assurance["signals_backend"] = signals_backend
    if archive_backend is not None:
        assurance["archive_backend"] = archive_backend
    if activation_policy is not None:
        assurance["activation_policy"] = activation_policy
    # A rewrite is lossy: PyYAML cannot round-trip comments, so re-dumping strips the
    # explanatory prose the settings document carries. Callers such as `arch-assurance init`
    # re-assert backends that are usually already correct, so writing unconditionally would
    # delete those comments while changing no setting. Only a real change is worth the cost.
    if data == before:
        return
    dumped = str(yaml.dump(data, default_flow_style=False, allow_unicode=True) or "")
    config_path.write_text(dumped, encoding="utf-8")

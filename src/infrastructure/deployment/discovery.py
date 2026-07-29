"""Operational-target discovery from one deployment manifest.

Only present surfaces become targets: an absent store or cache is no target and
is never initialized here (fresh-deployment initialization is a startup step,
not a migration). Physical identity is the canonical location + kind; the
co-located signal tables live inside the single `assurance_sqlcipher` target,
so one physical database opens exactly once.
"""

from __future__ import annotations

from pathlib import Path

from src.application.deployment_upgrade.ports import OperationalTargetHandle
from src.domain.deployment.layout import DeploymentManifest
from src.domain.repository.operational_upgrade import TargetKind, UpgradeTarget
from src.infrastructure.deployment.database_targets import (
    DatabaseTargetHandle,
    signal_schema_version,
    sqlcipher_connection_factory,
    sqlcipher_readable,
    sqlite_connection_factory,
)
from src.infrastructure.deployment.file_targets import (
    GuidanceCacheHandle,
    SettingsDocumentHandle,
    guidance_cache_version,
)


def _stable_id(kind: TargetKind, location: str) -> str:
    return f"{kind}:{location}"


def _stored_key(assurance_path: Path) -> str | None:
    """The key for the store at this path — credentials are scoped to the store they open."""
    from src.infrastructure.assurance import _credential_accounts as accounts  # noqa: PLC0415

    return accounts.read(accounts.DB_KEY, assurance_path)


def discover_operational_handles(
    manifest: DeploymentManifest,
) -> tuple[OperationalTargetHandle, ...]:
    handles: list[OperationalTargetHandle] = []

    settings_path = manifest.settings_document.path
    if manifest.settings_document.operator_owned and settings_path.is_file():
        handles.append(
            SettingsDocumentHandle(
                target=UpgradeTarget(
                    kind="deployment_settings",
                    stable_id=_stable_id("deployment_settings", str(settings_path)),
                    display_location=str(settings_path),
                    current_version=None,
                ),
                path=settings_path,
            )
        )

    cache_root = manifest.guidance_cache_root.path
    if cache_root.is_dir() and any(cache_root.glob("*.guidance.yaml")):
        handles.append(
            GuidanceCacheHandle(
                target=UpgradeTarget(
                    kind="guidance_cache",
                    stable_id=_stable_id("guidance_cache", str(cache_root)),
                    display_location=str(cache_root),
                    current_version=guidance_cache_version(cache_root),
                ),
                root=cache_root,
            )
        )

    signals_path = manifest.signals_db_path.path
    if signals_path.is_file():
        factory = sqlite_connection_factory(signals_path)
        version, inspectable = _probe_version(factory)
        handles.append(
            DatabaseTargetHandle(
                target=UpgradeTarget(
                    kind="signals_sqlite",
                    stable_id=_stable_id("signals_sqlite", str(signals_path)),
                    display_location=str(signals_path),
                    current_version=version,
                    configured=manifest.signals_backend == "sqlite",
                ),
                connect=factory,
                inspectable=inspectable,
            )
        )

    assurance_path = manifest.assurance_db_path.path
    if assurance_path.is_file():
        key = _stored_key(assurance_path)
        factory = sqlcipher_connection_factory(assurance_path, key) if key else None
        readable = factory is not None and sqlcipher_readable(factory)
        version = None
        if factory is not None and readable:
            version, readable = _probe_version(factory)
        handles.append(
            DatabaseTargetHandle(
                target=UpgradeTarget(
                    kind="assurance_sqlcipher",
                    stable_id=_stable_id("assurance_sqlcipher", str(assurance_path)),
                    display_location=str(assurance_path),
                    current_version=version,
                    credential_requirement="sqlcipher_key",
                    configured=manifest.store_backend == "sqlcipher",
                ),
                connect=factory if factory is not None else _never_connect(assurance_path),
                inspectable=readable,
            )
        )

    return tuple(handles)


def _probe_version(factory) -> tuple[int | None, bool]:  # type: ignore[no-untyped-def]
    try:
        conn = factory()
    except Exception:  # noqa: BLE001
        return None, False
    try:
        return signal_schema_version(conn), True
    except Exception:  # noqa: BLE001
        return None, False
    finally:
        conn.close()


def _never_connect(path):  # type: ignore[no-untyped-def]
    def connect():  # type: ignore[no-untyped-def]
        raise RuntimeError(
            f"No non-interactive credential available for the SQLCipher store at {path}; "
            "the target is uninspectable and must never be written."
        )

    return connect

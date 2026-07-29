"""Azure Blob Storage WORM archive adapter with container immutability policies.

Audit entries, baselines, and legal hold records are written to a container
protected by a time-based immutability policy or a locked immutability policy
(Azure Blob Storage). DEKs and mutable state objects (chain head, holds index)
are written to a separate *state* container without immutability constraints,
so they remain overwritable for state updates and deletable for shredding.

Azure prerequisites (portal / az CLI / ARM):
  1. Storage account with "Blob versioning" and "Immutable blob storage" enabled.
  2. Container-level time-based immutability policy applied to the archive container.
     Lock the policy for compliance-grade WORM (optional but recommended):
       az storage container immutability-policy lock ...
  3. The state container needs no special policies — standard RBAC access is enough.

Configuration (environment variables):
  ARCH_AZURE_STORAGE_ACCOUNT   required — storage account name
  ARCH_AZURE_CONTAINER         required — WORM archive container
  ARCH_AZURE_STATE_CONTAINER   optional — mutable state container
                                           (default: "{container}-state")
  ARCH_AZURE_STORAGE_KEY       optional — storage account key
                                           (omit to use DefaultAzureCredential)
  ARCH_AZURE_IMMUTABILITY_DAYS optional — retention display hint  (default: 365)

When ARCH_AZURE_STORAGE_KEY is absent the adapter uses DefaultAzureCredential
(azure-identity), which supports managed identities, workload identity, az login,
and env-var service principal (AZURE_TENANT_ID / AZURE_CLIENT_ID /
AZURE_CLIENT_SECRET).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from src.infrastructure.assurance._cloud_worm_base import (
    _DEK,
    _HEAD,
    _HOLDS_IDX,
    _CloudWORMBase,
)

logger = logging.getLogger(__name__)

_JSON_CONTENT_TYPE = "application/json"
_MUTABLE_KEYS = frozenset({_HEAD, _HOLDS_IDX})


def _is_mutable(key: str) -> bool:
    return key in _MUTABLE_KEYS or key.startswith(_DEK)


class AzureBlobWORMAssuranceArchive(_CloudWORMBase):
    """WORMAssuranceArchive backed by Azure Blob Storage with container immutability."""

    def __init__(
        self,
        account_name: str,
        container: str,
        *,
        state_container: str | None = None,
        account_key: str | None = None,
        immutability_days: int = 365,
    ) -> None:
        self._account_name = account_name
        self._container = container
        self._state_container = state_container or f"{container}-state"
        self._account_key = account_key
        self._immutability_days = immutability_days
        self._worm_client: Any = None
        self._state_client: Any = None

    @classmethod
    def from_env(cls) -> "AzureBlobWORMAssuranceArchive":
        account = os.environ.get("ARCH_AZURE_STORAGE_ACCOUNT", "")
        container = os.environ.get("ARCH_AZURE_CONTAINER", "")
        if not account or not container:
            raise RuntimeError(
                "archive_backend 'azure-blob-worm' requires ARCH_AZURE_STORAGE_ACCOUNT "
                "and ARCH_AZURE_CONTAINER env vars."
            )
        return cls(
            account_name=account,
            container=container,
            state_container=os.environ.get("ARCH_AZURE_STATE_CONTAINER") or None,
            account_key=os.environ.get("ARCH_AZURE_STORAGE_KEY") or None,
            immutability_days=int(os.environ.get("ARCH_AZURE_IMMUTABILITY_DAYS", "365")),
        )

    def _make_service(self) -> Any:
        from azure.storage.blob import BlobServiceClient  # type: ignore[import-untyped]  # noqa: PLC0415
        url = f"https://{self._account_name}.blob.core.windows.net"
        if self._account_key:
            return BlobServiceClient(account_url=url, credential=self._account_key)
        from azure.identity import DefaultAzureCredential  # type: ignore[import-untyped]  # noqa: PLC0415
        return BlobServiceClient(account_url=url, credential=DefaultAzureCredential())

    def _worm(self) -> Any:
        if self._worm_client is None:
            self._worm_client = self._make_service().get_container_client(self._container)
        return self._worm_client

    def _state(self) -> Any:
        if self._state_client is None:
            self._state_client = self._make_service().get_container_client(self._state_container)
        return self._state_client

    def _container_for(self, key: str) -> Any:
        return self._state() if _is_mutable(key) else self._worm()

    # ── Storage primitives ────────────────────────────────────────────────────

    def _read(self, key: str) -> dict[str, Any] | None:
        from azure.core.exceptions import ResourceNotFoundError  # type: ignore[import-untyped]  # noqa: PLC0415
        try:
            return json.loads(  # type: ignore[no-any-return]
                self._container_for(key).get_blob_client(key).download_blob().readall()
            )
        except ResourceNotFoundError:
            return None

    def _write_worm(self, key: str, data: dict[str, Any]) -> None:
        from azure.storage.blob import ContentSettings  # type: ignore[import-untyped]  # noqa: PLC0415
        self._worm().get_blob_client(key).upload_blob(
            json.dumps(data).encode(),
            overwrite=False,
            content_settings=ContentSettings(content_type=_JSON_CONTENT_TYPE),
        )

    def _write_mutable(self, key: str, data: dict[str, Any]) -> None:
        from azure.storage.blob import ContentSettings  # type: ignore[import-untyped]  # noqa: PLC0415
        self._state().get_blob_client(key).upload_blob(
            json.dumps(data).encode(),
            overwrite=True,
            content_settings=ContentSettings(content_type=_JSON_CONTENT_TYPE),
        )

    def _delete(self, key: str) -> None:
        self._state().get_blob_client(key).delete_blob()

    def _list_keys(self, prefix: str) -> list[str]:
        return sorted(b.name for b in self._worm().list_blobs(name_starts_with=prefix))

    def _apply_provider_legal_hold(self, *, activate: bool) -> None:
        try:
            # Container-level legal hold: prevents deletion of all blobs even after
            # the immutability policy period has expired.
            self._worm().set_legal_hold(activate)
            logger.info(
                "Azure WORM archive: legal hold %s (account=%s container=%s).",
                "ACTIVATED" if activate else "RELEASED",
                self._account_name, self._container,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "Azure WORM archive: legal hold state change failed (account=%s); "
                "verify container legal hold manually.",
                self._account_name, exc_info=True,
            )

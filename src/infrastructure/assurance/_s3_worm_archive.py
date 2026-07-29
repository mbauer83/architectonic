"""Amazon S3 Object Lock WORM archive adapter.

Each audit entry, baseline, and legal hold record is written as an S3 object
with time-based Object Lock retention. DEKs and mutable index objects (chain
head, holds index) are written WITHOUT Object Lock so they remain
overwritable for state updates and deletable for GDPR crypto-shredding.

Object Lock MUST be enabled on the S3 bucket at creation time:
    aws s3api create-bucket --object-lock-enabled-for-bucket ...

Configuration (environment variables):
  ARCH_S3_BUCKET               required — bucket name (Object Lock enabled)
  ARCH_S3_PREFIX               optional — key prefix  (default: "arch-assurance/")
  ARCH_S3_REGION               optional — AWS region override
  ARCH_S3_KMS_KEY_ID           optional — SSE-KMS key ARN/alias
  ARCH_S3_OBJECT_LOCK_MODE     optional — GOVERNANCE | COMPLIANCE  (default: GOVERNANCE)
  ARCH_S3_RETENTION_DAYS       optional — integer  (default: 365)

AWS credentials follow the standard boto3 chain: env vars (AWS_ACCESS_KEY_ID /
AWS_SECRET_ACCESS_KEY), ~/.aws/credentials, EC2 instance profile, ECS task
role, IAM Roles Anywhere, etc. No extra configuration is needed on AWS infra
with an appropriately scoped IAM role.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from src.infrastructure.assurance._cloud_worm_base import (
    _AUD,
    _BAS,
    _DEK,
    _HEAD,
    _HLD,
    _HOLDS_IDX,
    _CloudWORMBase,
)

logger = logging.getLogger(__name__)

_WORM_PREFIXES = (_AUD, _BAS, _HLD)


def _is_worm_key(key: str) -> bool:
    return any(key.startswith(p) for p in _WORM_PREFIXES)


class S3WORMAssuranceArchive(_CloudWORMBase):
    """WORMAssuranceArchive backed by Amazon S3 Object Lock."""

    def __init__(
        self,
        bucket: str,
        prefix: str = "arch-assurance/",
        *,
        region: str | None = None,
        kms_key_id: str | None = None,
        object_lock_mode: str = "GOVERNANCE",
        retention_days: int = 365,
    ) -> None:
        self._bucket = bucket
        self._prefix = prefix if prefix.endswith("/") else f"{prefix}/"
        self._region = region
        self._kms_key_id = kms_key_id
        self._object_lock_mode = object_lock_mode
        self._retention_days = retention_days
        self._client: Any = None

    @classmethod
    def from_env(cls) -> "S3WORMAssuranceArchive":
        bucket = os.environ.get("ARCH_S3_BUCKET", "")
        if not bucket:
            raise RuntimeError("archive_backend 's3-worm' requires ARCH_S3_BUCKET env var.")
        return cls(
            bucket=bucket,
            prefix=os.environ.get("ARCH_S3_PREFIX", "arch-assurance/"),
            region=os.environ.get("ARCH_S3_REGION") or None,
            kms_key_id=os.environ.get("ARCH_S3_KMS_KEY_ID") or None,
            object_lock_mode=os.environ.get("ARCH_S3_OBJECT_LOCK_MODE", "GOVERNANCE"),
            retention_days=int(os.environ.get("ARCH_S3_RETENTION_DAYS", "365")),
        )

    def _s3(self) -> Any:
        if self._client is None:
            import boto3  # type: ignore[import-untyped]  # noqa: PLC0415
            kwargs: dict[str, Any] = {}
            if self._region:
                kwargs["region_name"] = self._region
            self._client = boto3.client("s3", **kwargs)
        return self._client

    def _fk(self, key: str) -> str:
        return f"{self._prefix}{key}"

    # ── Storage primitives ────────────────────────────────────────────────────

    def _read(self, key: str) -> dict[str, Any] | None:
        import botocore.exceptions  # type: ignore[import-untyped]  # noqa: PLC0415
        try:
            body = self._s3().get_object(Bucket=self._bucket, Key=self._fk(key))["Body"].read()
            return json.loads(body)  # type: ignore[no-any-return]
        except botocore.exceptions.ClientError as exc:
            if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
                return None
            raise

    def _put(self, key: str, data: dict[str, Any], *, worm: bool) -> None:
        kwargs: dict[str, Any] = {
            "Bucket": self._bucket, "Key": self._fk(key),
            "Body": json.dumps(data).encode(), "ContentType": "application/json",
        }
        if worm:
            from datetime import datetime, timedelta, timezone  # noqa: PLC0415
            retain_until = (
                datetime.now(timezone.utc) + timedelta(days=self._retention_days)
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            kwargs["ObjectLockMode"] = self._object_lock_mode
            kwargs["ObjectLockRetainUntilDate"] = retain_until
        if self._kms_key_id:
            kwargs["ServerSideEncryption"] = "aws:kms"
            kwargs["SSEKMSKeyId"] = self._kms_key_id
        self._s3().put_object(**kwargs)

    def _write_worm(self, key: str, data: dict[str, Any]) -> None:
        self._put(key, data, worm=True)

    def _write_mutable(self, key: str, data: dict[str, Any]) -> None:
        self._put(key, data, worm=False)

    def _delete(self, key: str) -> None:
        self._s3().delete_object(Bucket=self._bucket, Key=self._fk(key))

    def _list_keys(self, prefix: str) -> list[str]:
        paginator = self._s3().get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=self._fk(prefix)):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"][len(self._prefix):])
        return sorted(keys)

    def _apply_provider_legal_hold(self, *, activate: bool) -> None:
        # Advisory: activating a legal hold does not apply per-object S3 legal holds
        # (that would require iterating all objects — cost-prohibitive). The primary
        # enforcement gate is the _holds_index check in shred_subject. Ensure your
        # bucket policy also blocks s3:DeleteObjectVersion during investigations.
        logger.info(
            "S3 WORM archive: legal hold %s (bucket=%s prefix=%s). "
            "Confirm bucket policy restricts deletion during active holds.",
            "ACTIVATED" if activate else "RELEASED",
            self._bucket, self._prefix,
        )

    # ── Mutable keys stay non-locked even when DEK store is in same bucket ────

    _MUTABLE = frozenset({_HEAD, _HOLDS_IDX})

    def _is_mutable(self, key: str) -> bool:
        return key in self._MUTABLE or key.startswith(_DEK)

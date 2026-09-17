"""What a release publishes, and whether downloaded bytes are what it said they were.

A release is the GitHub release a maintainer made: its version, the tag and the commit that tag
names, and the assets it carries, each with the digest the release states for it. `SHA256SUMS` is
the second statement of those digests, made by the build that produced the assets rather than by
the hosting; an asset is verified only when the bytes agree with **both**. This module is the one
reader of the `SHA256SUMS` line.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Literal

from src.application.software_update.version import ReleaseVersion

#: One line of `SHA256SUMS` as `sha256sum` writes it: the hex digest, two spaces (or a space and a
#: `*` for binary mode), the file name.
_CHECKSUM_LINE = re.compile(r"\A(?P<digest>[0-9a-fA-F]{64})(?:  | \*)(?P<name>.+)\Z")

CHECKSUMS_ASSET_NAME = "SHA256SUMS"


@dataclass(frozen=True)
class ReleaseAsset:
    """One file a release carries, with the digest the hosting states for it (None where it states none)."""

    name: str
    download_url: str
    stated_digest: str | None
    size: int


@dataclass(frozen=True)
class PublishedRelease:
    version: ReleaseVersion
    tag: str
    commit: str
    published_at: str
    prerelease: bool
    assets: tuple[ReleaseAsset, ...]

    def asset(self, name: str) -> ReleaseAsset | None:
        return next((asset for asset in self.assets if asset.name == name), None)

    @property
    def gui_bundle_name(self) -> str:
        return f"architectonic-gui-{self.version}.tar.gz"


@dataclass(frozen=True)
class ChecksumStatement:
    """The digests a `SHA256SUMS` file states, by file name."""

    digests: dict[str, str]

    @classmethod
    def parse(cls, text: str) -> ChecksumStatement:
        digests: dict[str, str] = {}
        for line in text.splitlines():
            if not line.strip():
                continue
            match = _CHECKSUM_LINE.match(line.strip())
            if match is None:
                raise ValueError(f"not a SHA256SUMS line: {line!r}")
            digests[match["name"]] = match["digest"].lower()
        return cls(digests)

    def digest_of(self, name: str) -> str | None:
        return self.digests.get(name)


VerificationVerdict = Literal["verified", "digest_mismatch", "no_statement"]


@dataclass(frozen=True)
class AssetVerification:
    """What comparing downloaded bytes with every digest statement found.

    `verified` needs at least one statement and agreement with every one present. A digest the
    hosting states and one the build states are independent sources, and both are checked when both
    exist; an asset with neither cannot be verified and is refused as such rather than assumed good.
    """

    asset: str
    verdict: VerificationVerdict
    actual_digest: str
    checked_against: tuple[str, ...]
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.verdict == "verified"


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().lower()


def verify_asset(
    data: bytes, asset: ReleaseAsset, statement: ChecksumStatement | None
) -> AssetVerification:
    """Compare *data* with the digest the hosting states and the digest the build states."""
    actual = sha256_of(data)
    statements: list[tuple[str, str]] = []
    if asset.stated_digest:
        statements.append(("release", asset.stated_digest.removeprefix("sha256:").lower()))
    stated_by_build = statement.digest_of(asset.name) if statement is not None else None
    if stated_by_build:
        statements.append((CHECKSUMS_ASSET_NAME, stated_by_build))
    if not statements:
        return AssetVerification(asset.name, "no_statement", actual, (), "no digest is stated for this asset")
    disagreeing = [source for source, digest in statements if digest != actual]
    if disagreeing:
        return AssetVerification(
            asset.name, "digest_mismatch", actual, tuple(source for source, _ in statements),
            f"the bytes do not match the digest stated by {', '.join(disagreeing)}",
        )
    return AssetVerification(asset.name, "verified", actual, tuple(source for source, _ in statements))

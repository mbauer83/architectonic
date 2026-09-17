"""The read-only half of an update: what is installed, what is released, and whether it can be trusted.

Everything here reads and compares; nothing here writes. The result is a value the CLI renders and,
under `--commit`, the apply half consumes — so the decision to move is always taken over a check that
has already happened, never re-derived while the installation is half-way moved.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.software_update.installation import InstalledSoftware
from src.application.software_update.plan import ReleaseVerification
from src.application.software_update.ports import Checkout, ReleaseSource
from src.application.software_update.release import (
    CHECKSUMS_ASSET_NAME,
    AssetVerification,
    ChecksumStatement,
    PublishedRelease,
    verify_asset,
)
from src.application.software_update.version import ReleaseVersion


@dataclass(frozen=True)
class ReleaseCheck:
    """What the dry run learned about the installation and the release it would move to."""

    installed: InstalledSoftware
    release: PublishedRelease | None
    #: The commit the fetched tag names, None when the tag is not on the origin.
    fetched_commit: str | None
    verification: ReleaseVerification | None
    #: Verified asset bytes by name, kept so the apply half installs what the check verified.
    assets: dict[str, bytes]

    @property
    def update_available(self) -> bool:
        return (
            self.release is not None
            and (self.installed.version is None or self.release.version > self.installed.version)
        )


def check_release(
    source: ReleaseSource,
    checkout: Checkout,
    *,
    requested: ReleaseVersion | None = None,
    include_prerelease: bool = False,
) -> ReleaseCheck:
    installed = checkout.observe()
    release = (
        source.by_version(requested) if requested is not None
        else source.latest(include_prerelease=include_prerelease)
    )
    if release is None:
        return ReleaseCheck(installed, None, None, None, {})
    if installed.version is not None and release.version <= installed.version:
        return ReleaseCheck(installed, release, None, None, {})

    fetched = checkout.fetch_tag(release.tag)
    signature = checkout.verify_tag(release.tag) if fetched is not None else "unsigned"
    assets, verifications = _verified_assets(source, release)
    verification = ReleaseVerification(
        commit_matches=fetched is not None and fetched == release.commit,
        signature=signature,
        assets=verifications,
        provenance="not_verified",
        provenance_detail="provenance attestations are not checked by this version",
    )
    return ReleaseCheck(installed, release, fetched, verification, assets)


def _verified_assets(
    source: ReleaseSource, release: PublishedRelease
) -> tuple[dict[str, bytes], tuple[AssetVerification, ...]]:
    """Download what the release carries that this installation would use, and check every digest.

    The checksum file is read first because it is the second statement every other asset is held
    to; an asset the release does not carry is simply not part of the plan (D4 decides what then).
    """
    statement: ChecksumStatement | None = None
    checksums = release.asset(CHECKSUMS_ASSET_NAME)
    if checksums is not None:
        statement = ChecksumStatement.parse(source.download(checksums).decode("utf-8"))
    wanted = release.asset(release.gui_bundle_name)
    if wanted is None:
        return {}, ()
    data = source.download(wanted)
    return {wanted.name: data}, (verify_asset(data, wanted, statement),)

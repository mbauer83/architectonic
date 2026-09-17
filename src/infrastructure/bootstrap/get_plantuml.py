"""
Download and verify plantuml.jar.

Primary source: Maven Central (SHA-256 verified via sidecar file).
Fallback source: GitHub Releases (no SHA-256 sidecar; size is reported).

Usage
-----
    get-plantuml                      # download pinned version → plantuml.jar
    get-plantuml --latest             # query GitHub API for newest release, then download
    get-plantuml --version 1.2026.3   # override version
    get-plantuml --output /tmp/p.jar  # custom output path
    get-plantuml --force              # re-download even if file already exists
    get-plantuml --check              # print SHA-256 of existing file, no download
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

from src.application.verification.artifact_verifier_syntax import PLANTUML_JAR_RELPATHS
from src.infrastructure.bootstrap.asset_download import download_bytes, download_verified, sha256_hex

# ── Pinned release ────────────────────────────────────────────────────────────
#
# License note (intentional): this fetches the plain `net.sourceforge.plantuml`
# artifact, which is GPLv3. That is deliberate, not an oversight. PlantUML is
# invoked strictly arm's-length (a separate `java -jar` subprocess), so under
# GPLv3's aggregation clause it does not affect the license of this project's own
# (MIT-licensed) code. Redistributing the unmodified jar in the image carries a
# notice + corresponding-source obligation, which is discharged in
# THIRD-PARTY-NOTICES (exact version + upstream source URL below). The permissive
# Maven editions (plantuml-mit/-epl/-lgpl) were evaluated and declined: they lag a
# release (max 1.2025.4 vs the pin here) and structural parity cannot guarantee
# subtle render fidelity for a dependency this central. Do not swap the artifact
# without re-opening that decision.

PLANTUML_VERSION = "1.2026.3"

_MAVEN_BASE = "https://repo1.maven.org/maven2/net/sourceforge/plantuml/plantuml"
_GITHUB_API_LATEST = "https://api.github.com/repos/plantuml/plantuml/releases/latest"
_GITHUB_DOWNLOAD = "https://github.com/plantuml/plantuml/releases/download/v{version}/plantuml-{version}.jar"

# ── Helpers ───────────────────────────────────────────────────────────────────


def _head_ok(url: str) -> bool:  # pragma: no cover — network HEAD request, not testable in unit tests
    """Return True if url responds with 2xx."""
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "get-plantuml/1.0"})
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            return resp.status < 300
    except Exception:
        return False


def _latest_github_version() -> str:  # pragma: no cover — network GitHub API, not testable in unit tests
    print(f"  querying: {_GITHUB_API_LATEST} … ", end="", flush=True)
    try:
        req = urllib.request.Request(_GITHUB_API_LATEST, headers={"User-Agent": "get-plantuml/1.0"})
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            data = json.loads(resp.read())
        tag = data["tag_name"].lstrip("v")
        print(tag)
        return tag
    except Exception as exc:
        print("FAILED")
        raise SystemExit(f"GitHub API error: {exc}") from exc


# ── Download strategies ───────────────────────────────────────────────────────


def _download_maven(version: str, output: Path) -> bool:  # pragma: no cover
    """Try Maven Central. Returns True on success, False if version not found there."""
    base = f"{_MAVEN_BASE}/{version}/plantuml-{version}"
    jar_url = f"{base}.jar"
    sha_url = f"{base}.jar.sha256"

    if not _head_ok(sha_url):
        print(f"  PlantUML {version} not yet on Maven Central — trying GitHub Releases")
        return False

    print(f"Downloading PlantUML {version} from Maven Central:")
    expected = download_bytes(sha_url, label="sha256").decode().strip().split()[0]
    jar_bytes = download_verified(jar_url, expected_sha256=expected, label="jar")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(jar_bytes)
    print(f"OK  {output}  ({len(jar_bytes):,} bytes, SHA-256 verified)")
    return True


def _download_github(version: str, output: Path) -> None:  # pragma: no cover
    """Download from GitHub Releases (no SHA-256 sidecar)."""
    jar_url = _GITHUB_DOWNLOAD.format(version=version)
    print(f"Downloading PlantUML {version} from GitHub Releases:")
    jar_bytes = download_bytes(jar_url, label="jar")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(jar_bytes)
    digest = sha256_hex(jar_bytes)
    print(f"OK  {output}  ({len(jar_bytes):,} bytes)")
    print(f"  SHA-256: {digest}  (no Maven Central sidecar to verify against)")


# ── Commands ──────────────────────────────────────────────────────────────────


def download(version: str, output: Path, *, force: bool) -> int:
    if output.exists() and not force:
        print(f"plantuml.jar already present at {output}")
        print("  (run with --force to re-download, or --check to verify)")
        return 0

    if not _download_maven(version, output):
        _download_github(version, output)
    return 0


def pinned_sidecar_digest(version: str = PLANTUML_VERSION) -> str | None:
    """The SHA-256 Maven Central states for `version`'s jar, or None when it cannot be fetched.

    None is "unverifiable", never "not pinned": an offline box must not be told its jar is wrong.
    """
    sidecar_url = f"{_MAVEN_BASE}/{version}/plantuml-{version}.jar.sha256"
    try:
        return download_bytes(sidecar_url).decode().strip().split()[0].lower()
    except (SystemExit, UnicodeDecodeError, IndexError):
        return None


def installed_jar_matches_pin(output: Path, version: str = PLANTUML_VERSION) -> bool | None:
    """Whether the jar at `output` is the release this source pins.

    True or False when Maven Central's sidecar could be read; None when it could not, or when there
    is no jar to compare. The updater asks this after moving the checkout, because a release may move
    the pin, and a jar left over from the previous pin renders with the previous PlantUML.
    """
    if not output.exists():
        return None
    expected = pinned_sidecar_digest(version)
    if expected is None:
        return None
    return sha256_hex(output.read_bytes()) == expected


def check(output: Path) -> int:
    """Print the jar's digest and whether it is the pinned release; exit 1 only when it is not."""
    if not output.exists():
        print(f"File not found: {output}")
        return 1
    digest = sha256_hex(output.read_bytes())
    print(f"{output}")
    print(f"  SHA-256: {digest}")
    verdict = installed_jar_matches_pin(output)
    if verdict is None:
        print(f"  pinned {PLANTUML_VERSION}: unverifiable (Maven Central sidecar not reachable)")
        return 0
    if verdict:
        print(f"  pinned {PLANTUML_VERSION}: yes")
        return 0
    print(f"  pinned {PLANTUML_VERSION}: NO — run get-plantuml --force to install the pinned release")
    return 1


# ── Entry point ───────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        default=None,
        metavar="VERSION",
        help=f"PlantUML version to download (default: {PLANTUML_VERSION})",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Query GitHub API for the newest release and download that version",
    )
    parser.add_argument(
        "--output",
        default=PLANTUML_JAR_RELPATHS[0],
        metavar="PATH",
        help=f"Destination path (default: {PLANTUML_JAR_RELPATHS[0]})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if the file already exists",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Print SHA-256 of the existing file without downloading",
    )
    args = parser.parse_args(argv)
    output = Path(args.output)

    if args.check:
        sys.exit(check(output))

    if args.latest:
        version = _latest_github_version()
    elif args.version:
        version = args.version
    else:
        version = PLANTUML_VERSION

    sys.exit(download(version, output, force=args.force))


if __name__ == "__main__":
    main()

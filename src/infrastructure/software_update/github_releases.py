"""Reading a repository's releases from the GitHub Releases API.

A release is what the maintainer published, not what a tag list contains; so the source of truth is
`/releases`, and the commit a release names is resolved through the tag object rather than trusted
from `target_commitish`, which is a branch. The client is injectable so every failure path is
testable without a network, as `osv_client` does for OSV.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

import httpx

from src.application.software_update.ports import ReleaseSourceError
from src.application.software_update.release import PublishedRelease, ReleaseAsset
from src.application.software_update.version import NotAReleaseVersion, ReleaseVersion, parse_release_version

GITHUB_API = "https://api.github.com"
_TIMEOUT_SECONDS = 30.0
_USER_AGENT = "architectonic-update/1.0"


def token_from_environment(environ: Mapping[str, str] | None = None) -> str | None:
    """A token raises the rate limit; it is never required."""
    env = os.environ if environ is None else environ
    return env.get("GITHUB_TOKEN") or env.get("GH_TOKEN") or None


class GitHubReleases:
    def __init__(
        self,
        repository: str,
        *,
        http: httpx.Client | None = None,
        token: str | None = None,
        api_base: str = GITHUB_API,
    ) -> None:
        if repository.count("/") != 1:
            raise ValueError(f"update.repository must be 'owner/repo', got {repository!r}")
        self._repository = repository
        headers = {"Accept": "application/vnd.github+json", "User-Agent": _USER_AGENT}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = http or httpx.Client(timeout=_TIMEOUT_SECONDS, headers=headers, follow_redirects=True)
        self._headers = headers
        self._api = api_base.rstrip("/")

    # ── ReleaseSource ─────────────────────────────────────────────────────────

    def latest(self, *, include_prerelease: bool) -> PublishedRelease | None:
        if not include_prerelease:
            payload = self._get(f"/repos/{self._repository}/releases/latest", allow_404=True)
            return self._release(payload) if payload is not None else None
        releases: list[dict[str, Any]] = self._get(f"/repos/{self._repository}/releases", params={"per_page": 30}) or []
        candidates = [self._release(item) for item in releases if not item.get("draft")]
        return max(candidates, key=lambda release: release.version, default=None)

    def by_version(self, version: ReleaseVersion) -> PublishedRelease | None:
        payload = self._get(f"/repos/{self._repository}/releases/tags/{version.tag}", allow_404=True)
        return self._release(payload) if payload is not None else None

    def download(self, asset: ReleaseAsset) -> bytes:
        try:
            headers = {**self._headers, "Accept": "application/octet-stream"}
            response = self._http.get(asset.download_url, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ReleaseSourceError(f"downloading {asset.name}: {exc}") from exc
        return response.content

    # ── The API ───────────────────────────────────────────────────────────────

    def _get(self, path: str, *, params: dict[str, Any] | None = None, allow_404: bool = False) -> Any:
        try:
            response = self._http.get(f"{self._api}{path}", params=params, headers=self._headers)
        except httpx.HTTPError as exc:
            raise ReleaseSourceError(f"GitHub API {path}: {exc}") from exc
        if response.status_code == 404 and allow_404:
            return None
        if response.status_code in (403, 429) and response.headers.get("x-ratelimit-remaining") == "0":
            reset = response.headers.get("x-ratelimit-reset", "unknown")
            raise ReleaseSourceError(
                f"GitHub API rate limit reached (resets at epoch {reset}); set GITHUB_TOKEN to raise it"
            )
        if response.status_code >= 400:
            raise ReleaseSourceError(f"GitHub API {path} answered {response.status_code}")
        return response.json()

    def _release(self, payload: Mapping[str, Any]) -> PublishedRelease:
        tag = str(payload.get("tag_name") or "")
        try:
            version = parse_release_version(tag)
        except NotAReleaseVersion as exc:
            raise ReleaseSourceError(f"release tag {tag!r} is not a release version") from exc
        assets = tuple(
            ReleaseAsset(
                name=str(asset["name"]),
                download_url=str(asset["browser_download_url"]),
                stated_digest=_digest(asset.get("digest")),
                size=int(asset.get("size") or 0),
            )
            for asset in payload.get("assets") or []
        )
        return PublishedRelease(
            version=version,
            tag=tag,
            commit=self._commit_of_tag(tag),
            published_at=str(payload.get("published_at") or ""),
            prerelease=bool(payload.get("prerelease")),
            assets=assets,
        )

    def _commit_of_tag(self, tag: str) -> str:
        """The commit a tag names: through the tag object for an annotated tag, directly otherwise."""
        ref = self._get(f"/repos/{self._repository}/git/ref/tags/{tag}")
        target = ref["object"]
        if target["type"] == "tag":
            tag_object = self._get(f"/repos/{self._repository}/git/tags/{target['sha']}")
            return str(tag_object["object"]["sha"])
        return str(target["sha"])


def _digest(raw: object) -> str | None:
    if not isinstance(raw, str) or not raw:
        return None
    return raw.removeprefix("sha256:").lower()

"""The release source reads what the maintainer published and resolves the commit a tag names."""

from __future__ import annotations

import json

import httpx
import pytest

from src.application.software_update.ports import ReleaseSourceError
from src.application.software_update.version import ReleaseVersion
from src.infrastructure.software_update.github_releases import GitHubReleases, token_from_environment

REPO = "mbauer83/architectonic"
COMMIT = "9bac48609abee457e03ba294a9e6c44601ceca10"
TAG_OBJECT = "1111111111111111111111111111111111111111"


def _release_json(tag: str, *, prerelease: bool = False, draft: bool = False) -> dict:
    return {
        "tag_name": tag, "published_at": "2026-10-02T09:00:00Z", "prerelease": prerelease, "draft": draft,
        "assets": [
            {
                "name": f"architectonic-gui-{tag[1:]}.tar.gz",
                "browser_download_url": f"https://github.com/{REPO}/releases/download/{tag}/gui.tgz",
                "size": 12, "digest": "sha256:" + "A" * 64,
            },
            {
                "name": "SHA256SUMS", "size": 90,
                "browser_download_url": f"https://github.com/{REPO}/releases/download/{tag}/SHA256SUMS",
            },
        ],
    }


def _transport(routes: dict[str, object], *, rate_limited: bool = False) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        if rate_limited:
            return httpx.Response(403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1700000000"})
        key = request.url.path if request.url.host == "api.github.com" else str(request.url)
        if key not in routes:
            return httpx.Response(404, json={"message": "Not Found"})
        body = routes[key]
        if isinstance(body, bytes):
            return httpx.Response(200, content=body)
        return httpx.Response(200, json=body)
    return httpx.MockTransport(handle)


def _source(routes: dict[str, object], **kwargs: object) -> GitHubReleases:
    return GitHubReleases(REPO, http=httpx.Client(transport=_transport(routes, **kwargs)))  # type: ignore[arg-type]


ANNOTATED_TAG_ROUTES = {
    f"/repos/{REPO}/releases/latest": _release_json("v0.10.1"),
    f"/repos/{REPO}/git/ref/tags/v0.10.1": {"object": {"type": "tag", "sha": TAG_OBJECT}},
    f"/repos/{REPO}/git/tags/{TAG_OBJECT}": {"object": {"type": "commit", "sha": COMMIT}},
}


def test_the_latest_release_resolves_its_commit_through_the_annotated_tag_object() -> None:
    release = _source(ANNOTATED_TAG_ROUTES).latest(include_prerelease=False)

    assert release is not None
    assert release.version == ReleaseVersion(0, 10, 1) and release.tag == "v0.10.1"
    assert release.commit == COMMIT
    assert release.asset("architectonic-gui-0.10.1.tar.gz").stated_digest == "a" * 64  # type: ignore[union-attr]
    assert release.asset("SHA256SUMS").stated_digest is None  # type: ignore[union-attr]


def test_a_lightweight_tag_names_its_commit_directly() -> None:
    routes = {
        f"/repos/{REPO}/releases/tags/v0.10.2": _release_json("v0.10.2"),
        f"/repos/{REPO}/git/ref/tags/v0.10.2": {"object": {"type": "commit", "sha": COMMIT}},
    }
    release = _source(routes).by_version(ReleaseVersion(0, 10, 2))
    assert release is not None and release.commit == COMMIT


def test_no_release_and_an_unknown_version_answer_none() -> None:
    assert _source({}).latest(include_prerelease=False) is None
    assert _source({}).by_version(ReleaseVersion(9, 9, 9)) is None


def test_prereleases_are_excluded_unless_asked_for_and_drafts_never_count() -> None:
    routes = {
        f"/repos/{REPO}/releases": [
            _release_json("v0.11.0", prerelease=True), _release_json("v0.10.1"), _release_json("v0.12.0", draft=True),
        ],
        f"/repos/{REPO}/releases/latest": _release_json("v0.10.1"),
        f"/repos/{REPO}/git/ref/tags/v0.11.0": {"object": {"type": "commit", "sha": COMMIT}},
        f"/repos/{REPO}/git/ref/tags/v0.10.1": {"object": {"type": "commit", "sha": COMMIT}},
    }
    assert _source(routes).latest(include_prerelease=False).version == ReleaseVersion(0, 10, 1)  # type: ignore[union-attr]
    assert _source(routes).latest(include_prerelease=True).version == ReleaseVersion(0, 11, 0)  # type: ignore[union-attr]


def test_a_download_returns_the_bytes_and_a_failure_names_the_asset() -> None:
    release = _source(ANNOTATED_TAG_ROUTES).latest(include_prerelease=False)
    assert release is not None
    sums = release.asset("SHA256SUMS")
    assert sums is not None
    routes = {**ANNOTATED_TAG_ROUTES, sums.download_url: b"abc"}

    assert _source(routes).download(sums) == b"abc"
    with pytest.raises(ReleaseSourceError, match="SHA256SUMS"):
        _source(ANNOTATED_TAG_ROUTES).download(sums)


def test_the_rate_limit_is_reported_with_its_reset_and_the_token_hint() -> None:
    with pytest.raises(ReleaseSourceError, match="rate limit.*1700000000.*GITHUB_TOKEN"):
        _source({}, rate_limited=True).latest(include_prerelease=False)


def test_a_tag_that_is_not_a_release_version_is_refused_by_name() -> None:
    routes = {f"/repos/{REPO}/releases/latest": _release_json("nightly-2026")}
    with pytest.raises(ReleaseSourceError, match="nightly-2026"):
        _source(routes).latest(include_prerelease=False)


def test_the_repository_must_be_owner_slash_repo() -> None:
    with pytest.raises(ValueError):
        GitHubReleases("architectonic")


def test_the_token_is_optional_and_read_from_either_variable() -> None:
    assert token_from_environment({}) is None
    assert token_from_environment({"GH_TOKEN": "x"}) == "x"
    assert token_from_environment({"GITHUB_TOKEN": "y", "GH_TOKEN": "x"}) == "y"
    assert json.dumps(token_from_environment({"GITHUB_TOKEN": ""})) == "null"

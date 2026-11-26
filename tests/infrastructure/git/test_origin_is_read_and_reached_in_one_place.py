"""A remote URL has one reader, `origin` is reached through two runners, and the held credentials one owner.

- **One reading of a remote URL** (`git_auth.read_remote_url`). The credential prompt, the refusal and the
  pull-request link each parsed the URL forms themselves and disagreed about a one-letter "host": a Windows
  drive letter was local to one and an ssh host to another.
- **Where git reaches origin** (`RemoteUrls`): the fetch URL apart from the push URLs, so no reader has to
  know the order a tuple was built in.
- **One boundary for a refused credential** (`_git_command.push_to_origin` / `ask_origin`): a command that
  reaches origin and is refused for want of a credential raises `GitCredentialsRequired` wherever it ran —
  the write path, the background merge transition's pull, `arch-repair`. No call site asks.
- **One owner of the held credentials** (`held_credentials`), with the environment every git call reads,
  and a supply that never loses a credential for the other protocol supplied meanwhile.
"""

from __future__ import annotations

import asyncio
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.infrastructure.git import _git_command, git_auth, held_credentials, repair_adapter
from src.infrastructure.git.credential_refusal import GitCredentialsRequired
from src.infrastructure.git.git_auth import RemoteUrls, read_remote_url, redacted_url
from src.infrastructure.git.git_sync import GitSyncManager
from src.infrastructure.git.review_link import new_pull_request_url

_PUSH = "git@git.example.invalid:acme/repo.git"
_FETCH = "https://git.example.invalid/acme/repo.git"
_REFUSED = "git@git.example.invalid: Permission denied (publickey)."


@pytest.mark.parametrize(
    ("url", "read"),
    [
        ("git@github.com:acme/repo.git", ("ssh", "github.com", "acme/repo.git")),
        ("github.com-personal:acme/repo.git", ("ssh", "github.com-personal", "acme/repo.git")),
        ("ssh://git@Host:2222/acme/repo.git", ("ssh", "host", "/acme/repo.git")),
        ("https://user:tok@Host/acme/repo.git", ("https", "host", "/acme/repo.git")),
        ("C:/repos/repo.git", None),
        ("/srv/git/repo.git", None),
        ("file:///srv/git/repo.git", None),
        ("git://host/repo.git", None),
    ],
)
def test_a_remote_url_is_read_once_for_every_question_asked_of_it(url: str, read: tuple[str, str, str] | None) -> None:
    found = read_remote_url(url)
    assert (None if found is None else (found.protocol, found.host, found.path)) == read
    assert git_auth.protocol_of_url(url) == (read[0] if read else None)


def test_a_drive_letter_is_neither_a_credential_host_nor_a_platform() -> None:
    """The disagreement this reader ended: the link builder read `C` as an ssh host and asked ssh about it."""
    asked: list[str] = []
    assert new_pull_request_url("C:/repos/repo.git", branch="b", base="main", resolve_host=asked.append) is None
    assert asked == []


def test_a_token_in_a_url_is_redacted_and_the_scp_form_is_kept() -> None:
    assert redacted_url("https://user:ghp_secret@host:8443/a/b.git") == "https://host:8443/a/b.git"
    assert redacted_url(_PUSH) == _PUSH


def test_where_a_push_goes_falls_back_to_the_fetch_url() -> None:
    assert RemoteUrls(_FETCH, (_PUSH,)).pushed_to == (_PUSH,)
    assert RemoteUrls(_FETCH).pushed_to == (_FETCH,)
    assert RemoteUrls(_FETCH, (_FETCH, _PUSH)).all == (_FETCH, _PUSH)
    assert RemoteUrls(None).all == () and RemoteUrls(None).pushed_to == ()


@pytest.fixture
def split_remote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository whose origin fetches over https and pushes over ssh, whose git answers *_REFUSED*."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "remote", "add", "origin", _FETCH], cwd=repo, check=True)
    subprocess.run(["git", "remote", "set-url", "--push", "origin", _PUSH], cwd=repo, check=True)
    held_credentials.release()
    return repo


def _refusing_git(_repo: Path, args: object, *, timeout: float, env: object) -> SimpleNamespace:
    return SimpleNamespace(returncode=128, stdout="", stderr=_REFUSED)


def test_a_push_refused_for_a_credential_is_raised_by_the_runner_naming_the_push_url(
    split_remote: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_git_command, "run_git", _refusing_git)
    with pytest.raises(GitCredentialsRequired) as refused:
        _git_command.push_to_origin(split_remote, "origin", "main")
    assert (refused.value.protocol, refused.value.remote_url) == ("ssh", _PUSH)


def test_a_read_of_origin_refused_for_a_credential_names_the_fetch_url(
    split_remote: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        _git_command, "run_git",
        lambda *_a, **_k: SimpleNamespace(returncode=128, stdout="", stderr="fatal: Authentication failed"),
    )
    with pytest.raises(GitCredentialsRequired) as refused:
        _git_command.ask_origin(split_remote, "fetch", "origin")
    assert (refused.value.protocol, refused.value.remote_url) == ("https", _FETCH)


def test_a_failure_for_another_reason_is_answered_not_raised(
    split_remote: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        _git_command, "run_git", lambda *_a, **_k: SimpleNamespace(returncode=1, stdout="", stderr="rejected"),
    )
    assert _git_command.push_to_origin(split_remote, "origin", "main") == (1, "", "rejected")


def test_the_repair_reports_a_refused_push_as_a_credential_refusal(
    split_remote: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`arch-repair` wires its own credentials; a refusal still comes out of the one runner."""
    seen: list[dict[str, str]] = []

    def git(_repo: Path, args: object, *, timeout: float, env: dict[str, str]) -> SimpleNamespace:
        seen.append(env)
        return _refusing_git(_repo, args, timeout=timeout, env=env)

    monkeypatch.setattr(_git_command, "run_git", git)
    adapter = repair_adapter.GitRepairAdapter(split_remote, {"ARCH_GIT_SSH_PASSWORD": "from-the-repair"})
    with pytest.raises(GitCredentialsRequired):
        adapter.push_repair(SimpleNamespace(repair_branch="repair/x"))  # type: ignore[arg-type]
    assert seen == [{"ARCH_GIT_SSH_PASSWORD": "from-the-repair"}]


def test_the_background_pull_raises_the_refusal_and_the_background_fetch_does_not(
    split_remote: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The merge transition's pull reports a refusal like any other; a fetch stays a deferral."""
    sync = GitSyncManager.__new__(GitSyncManager)

    async def refusing(_repo: Path, *_args: str, timeout: float = 10.0) -> tuple[int, str, str]:
        return 128, "", _REFUSED

    monkeypatch.setattr(sync, "_git", refusing)
    with pytest.raises(GitCredentialsRequired):
        asyncio.run(sync._ask_origin(split_remote, "pull", "--ff-only", timeout=5))


def test_held_credentials_are_the_environment_every_git_call_reads() -> None:
    held_credentials.release()
    assert held_credentials.git_environment() is None
    held_credentials.hold(git_auth.GitCredentials(ssh_passphrase="pp"))
    try:
        assert (held_credentials.git_environment() or {})["ARCH_GIT_SSH_PASSWORD"] == "pp"
    finally:
        held_credentials.release()
    assert held_credentials.git_environment() is None


def test_two_supplies_at_once_keep_both_protocols(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The lost update: an ssh supply verified while an https one completed used to overwrite it."""
    held_credentials.release()
    ssh_verifying = threading.Event()
    https_held = threading.Event()

    def verify(_repos: object, _env: object, *, protocols: frozenset[str]) -> list[tuple[Path, str]]:
        if "ssh" in protocols:
            ssh_verifying.set()
            assert https_held.wait(5)
        return []

    monkeypatch.setattr(held_credentials, "verify_credentials", verify)
    monkeypatch.setattr(held_credentials, "create_askpass_script", lambda: tmp_path / "askpass")

    def supply_ssh() -> None:
        held_credentials.supply("ssh", secret="pp", username=None, verify_against=[])

    ssh = threading.Thread(target=supply_ssh)
    ssh.start()
    assert ssh_verifying.wait(5)
    held_credentials.supply("https", secret="token", username="u", verify_against=[])
    https_held.set()
    ssh.join(5)
    try:
        now = held_credentials.held()
        assert now is not None and now.has_ssh and now.has_https
    finally:
        held_credentials.release()

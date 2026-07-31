"""Writing a credential over its own protection — the bug that cost a working assurance store.

`_DPAPIBackend.set` chmod-protects every credential file after writing it, and `Export-Clixml`
cannot overwrite a read-only file. So the store made itself unwritable: with the files at `0400` on
disk, every subsequent write failed. PowerShell exited 1, `capture_output=True` swallowed its stderr,
and `check=True` surfaced a bare `CalledProcessError` echoing the whole command and no reason.

What that cost: `arch-assurance unlock` writes the setup gate *before* it authorises the running
backend, so the failure meant the authorisation step never ran. A restarted backend could not be
unlocked, and the error said nothing about permissions.

Two properties, and both matter in opposite directions:

* the write must **succeed** over an existing protected file — otherwise the store is write-once;
* the protection must **come back**, at the mode the file already had. Hardening to `0400` out of
  band is a deliberate act (keys have been lost here), and a rewrite must not quietly relax it to
  `0600`.

No PowerShell is invoked: the subprocess call is stubbed, so this runs anywhere and cannot reach a
real keychain. `_DPAPIBackend` is constructed directly rather than selected, so the suite's
forbid-real-backend gate is not involved — and the credentials directory is already redirected to a
throwaway by `tests/conftest.py`.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

from src.infrastructure.assurance import _credential_store as creds

_ACCOUNT = "setup-confirmed-probe"


@pytest.fixture()
def backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """A DPAPI backend over a throwaway directory, with PowerShell stubbed out."""
    monkeypatch.setenv("ARCH_ASSURANCE_CREDENTIALS_DIR", str(tmp_path / "config"))
    built = creds._DPAPIBackend()  # noqa: SLF001 — constructed, never selected
    # `wslpath` may not exist wherever this runs, and the Windows path is not what is under test.
    monkeypatch.setattr(type(built), "_win", staticmethod(lambda path: f"C:\\fake\\{Path(path).name}"))
    return built


def _stub_powershell(monkeypatch: pytest.MonkeyPatch, backend: Any, *, returncode: int = 0,
                     stderr: str = "") -> list[int | None]:
    """Replace the subprocess call, recording the target's mode at the moment of the write."""
    observed: list[int | None] = []
    target = backend._path(_ACCOUNT)  # noqa: SLF001

    def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        observed.append(
            stat.S_IMODE(target.stat().st_mode) if target.exists() else None
        )
        if returncode == 0:
            target.write_text("clixml-payload", encoding="utf-8")
        return subprocess.CompletedProcess(argv, returncode, "", stderr)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return observed


class TestWritingOverAProtectedFile:
    def test_it_succeeds(self, backend: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """The bug. A file at 0400 could not be rewritten, so the store was write-once."""
        target = backend._path(_ACCOUNT)  # noqa: SLF001
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("old", encoding="utf-8")
        os.chmod(target, 0o400)
        _stub_powershell(monkeypatch, backend)

        backend.set(_ACCOUNT, "1")

        assert target.read_text(encoding="utf-8") == "clixml-payload"

    def test_the_file_is_writable_at_the_moment_of_the_write(
        self, backend: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The mechanism, asserted where it acts: PowerShell cannot write a read-only file, so the
        protection has to be relaxed *before* the subprocess, not merely restored after."""
        target = backend._path(_ACCOUNT)  # noqa: SLF001
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("old", encoding="utf-8")
        os.chmod(target, 0o400)
        observed = _stub_powershell(monkeypatch, backend)

        backend.set(_ACCOUNT, "1")

        assert observed == [0o600], "the write ran against a mode PowerShell would have refused"

    def test_the_original_protection_comes_back(
        self, backend: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A file hardened to 0400 stays hardened. Relaxing it to 0600 on every write would undo a
        deliberate protection silently, which is how a key becomes writable by accident."""
        target = backend._path(_ACCOUNT)  # noqa: SLF001
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("old", encoding="utf-8")
        os.chmod(target, 0o400)
        _stub_powershell(monkeypatch, backend)

        backend.set(_ACCOUNT, "1")

        assert stat.S_IMODE(target.stat().st_mode) == 0o400


class TestReadingReportsWhatItKnows:
    """A read distinguishes "there is no such credential" from "I could not read it".

    Flattening the two into ``None`` cost the live store on 2026-07-31: a ``powershell.exe`` spawn that
    timed out under load looked exactly like an unconfigured store, and the caller acted on it. See
    ``tests/assurance/test_credential_read_is_not_a_write.py`` for what the caller then did.
    """

    def test_a_missing_credential_reads_as_none(self, backend: Any) -> None:
        assert backend.get("never-written") is None

    def test_a_failed_read_raises_rather_than_reporting_absence(
        self, backend: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = backend._path(_ACCOUNT)  # noqa: SLF001
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("clixml", encoding="utf-8")

        def timing_out(*_args: object, **_kwargs: object) -> str:
            raise subprocess.TimeoutExpired(cmd="powershell.exe", timeout=15)

        monkeypatch.setattr(subprocess, "check_output", timing_out)

        with pytest.raises(creds.CredentialUnavailable):
            backend.get(_ACCOUNT)

    def test_a_credential_that_decrypts_to_nothing_is_damaged_not_absent(
        self, backend: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An existing file yielding an empty value is a broken credential. Reported as absence it
        would invite exactly the same false-absence handling as a timeout."""
        target = backend._path(_ACCOUNT)  # noqa: SLF001
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("clixml", encoding="utf-8")
        monkeypatch.setattr(subprocess, "check_output", lambda *_a, **_k: "   \n")

        with pytest.raises(creds.CredentialUnavailable):
            backend.get(_ACCOUNT)

    def test_a_successful_read_returns_the_value(
        self, backend: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = backend._path(_ACCOUNT)  # noqa: SLF001
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("clixml", encoding="utf-8")
        monkeypatch.setattr(subprocess, "check_output", lambda *_a, **_k: "the-key\n")

        assert backend.get(_ACCOUNT) == "the-key"


class TestWritingANewFile:
    def test_it_is_protected_to_0600(self, backend: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """A credential is never left group- or world-readable, even for the moment before a
        subsequent hardening step runs."""
        _stub_powershell(monkeypatch, backend)

        backend.set(_ACCOUNT, "1")

        target = backend._path(_ACCOUNT)  # noqa: SLF001
        assert stat.S_IMODE(target.stat().st_mode) == 0o600

    def test_the_directory_is_owner_only(
        self, backend: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_powershell(monkeypatch, backend)

        backend.set(_ACCOUNT, "1")

        assert stat.S_IMODE(backend._creds.stat().st_mode) == 0o700  # noqa: SLF001


class TestAFailedWrite:
    def test_it_reports_what_powershell_said(
        self, backend: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The second half of the incident. A `CalledProcessError` naming the whole command and no
        reason is what made a permission problem look like an environment mystery."""
        _stub_powershell(monkeypatch, backend, returncode=1, stderr="Access to the path is denied.")

        with pytest.raises(RuntimeError) as raised:
            backend.set(_ACCOUNT, "1")

        assert "Access to the path is denied." in str(raised.value)
        assert _ACCOUNT in str(raised.value)

    def test_it_does_not_echo_the_credential(
        self, backend: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The value is on the command line, so the command line must never reach a log or a
        traceback — which is exactly what the old `CalledProcessError` did."""
        _stub_powershell(monkeypatch, backend, returncode=1, stderr="denied")

        with pytest.raises(RuntimeError) as raised:
            backend.set(_ACCOUNT, "super-secret-key-material")

        assert "super-secret-key-material" not in str(raised.value)

    def test_a_failure_leaves_the_protection_in_place(
        self, backend: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A write that did not happen must not leave the file writable behind it."""
        target = backend._path(_ACCOUNT)  # noqa: SLF001
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("old", encoding="utf-8")
        os.chmod(target, 0o400)
        _stub_powershell(monkeypatch, backend, returncode=1, stderr="denied")

        with pytest.raises(RuntimeError):
            backend.set(_ACCOUNT, "1")

        assert stat.S_IMODE(target.stat().st_mode) == 0o400, (
            "a failed write left the credential file loosened"
        )

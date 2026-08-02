"""`GET /api/assurance/status` reports the store the rest of the product is using.

This route is the only thing the GUI's locked/unlocked banner reads, and it is the operator's whole
view of the confidential store from inside the application. It had no test, and it was wrong: the store
path was a literal — `Path(__file__).resolve().parents[4] / ".arch-assurance" / "store.db"` — one level
short of the repository root, so it named `src/.arch-assurance/store.db`, which has never existed.

The consequences ran the wrong way round from the usual "it says broken when it works":

* `db_exists` was always False and `configured` always False, whatever was on disk.
* A store that existed and was merely **locked** therefore reported `not_initialised`.
* The remedy for `not_initialised` is `arch-assurance init`, which generates a new encryption key and
  puts it where the old one was. Losing that key has cost this repository its store four times. A
  status route that steers an operator toward `init` on a perfectly good locked store is the most
  expensive kind of wrong a read-only endpoint can be.

And the reason nothing noticed: the *key* lookup succeeded anyway. `_credential_accounts.read` falls
back to the legacy unscoped account when the path-scoped one is absent — deliberately, so a store
predating the scoping keeps opening — so `key_in_keychain: true` came back for a path that named
nothing. A wrong path looked like a working one.

So the tests here are about **agreement**: the route resolves the same store as the CLI and the MCP tool
do, and it describes what is actually on disk rather than what a literal predicted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


@pytest.fixture()
def client() -> Any:
    """Only the assurance router: this route reads no repository, and mounting one would give the test
    a second reason to fail."""
    from starlette.testclient import TestClient

    from src.infrastructure.rest.routers.assurance.router import router as assurance_router
    from tests.support.api_app import build_api_app

    return TestClient(build_api_app(assurance_router))


def test_the_route_resolves_the_same_store_as_the_cli_and_the_mcp_tool() -> None:
    """One store, three readers, one resolver.

    Asserted as delegation rather than as equal strings: the manifest honours a CLI flag, a settings
    key and `ARCH_ASSURANCE_DB_PATH`, none of which a literal in a router could ever have honoured, so
    "they agree today" is weaker than "they ask the same question".
    """
    from src.infrastructure.cli._assurance_commands import _default_db_path as cli_path
    from src.infrastructure.mcp.assurance_mcp.context import default_db_path as mcp_path
    from src.infrastructure.rest.routers.assurance.router import _store_path as rest_path

    assert rest_path() == mcp_path() == cli_path()


def test_the_resolved_store_is_not_inside_the_source_tree() -> None:
    """The exact shape of the defect, named so it cannot come back as a different off-by-one.

    `src/` is where the mistaken literal pointed. A store there would be inside the packaged wheel's
    own tree, which is the one place a confidential database must never be.
    """
    from src.infrastructure.rest.routers.assurance.router import _store_path

    assert "src" not in _store_path().parts[-3:], _store_path()


class TestWhatItReportsAboutADiskThatExists:
    """Driven through `ARCH_ASSURANCE_DB_PATH`, so the assertions are about a store this test owns.

    Not the developer's store: its lock state is whatever the last `unlock` left, and a test that read
    it would pass or fail on that. The override is the manifest's own documented input.
    """

    @pytest.fixture(autouse=True)
    def _own_store(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        store = tmp_path / ".arch-assurance" / "store.db"
        store.parent.mkdir(parents=True)
        # Bytes, not a real SQLCipher database: what is under test is the *reporting* of a file's
        # existence. Making it a real store would need a key in the OS keychain, and writing one from a
        # test is how this repository lost its store the first time.
        store.write_bytes(b"not a real store, and this route must not care")
        monkeypatch.setenv("ARCH_ASSURANCE_DB_PATH", str(store))
        self._reset_manifest()
        yield
        monkeypatch.delenv("ARCH_ASSURANCE_DB_PATH", raising=False)
        self._reset_manifest()

    @staticmethod
    def _reset_manifest() -> None:
        from src.infrastructure.deployment.layout import resolve_manifest

        cache_clear = getattr(resolve_manifest, "cache_clear", None)
        if cache_clear is not None:
            cache_clear()

    def test_a_store_on_disk_is_reported_as_existing(self, client: Any) -> None:
        """The narrowest statement of the defect: a file that is there is reported as there."""
        response = client.get("/api/assurance/status")

        assert response.status_code == 200, response.text
        assert response.json()["db_exists"] is True

    def test_a_store_with_its_key_is_reported_as_locked_rather_than_uninitialised(
        self, client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The regression, at the state that matters: existing, keyed, and not held open.

        The key presence is substituted rather than arranged. Writing a key into the OS credential
        store from a test is how this repository lost its store the first time, and the boundary being
        stood in for is a `powershell.exe` spawn on WSL2 — not the thing under test, which is what the
        route *derives* from the answer.
        """
        from src.infrastructure.assurance import _credential_accounts as accounts

        monkeypatch.setattr(accounts, "present", lambda _base, _path: True)

        payload = client.get("/api/assurance/status").json()

        if payload["unlocked"]:
            pytest.skip("this process holds the store open, so there is no locked state to report")
        assert payload["configured"] is True, payload
        assert payload["status"] == "locked", payload

    def test_a_store_whose_key_is_gone_stays_distinguishable_from_one_never_made(
        self, client: Any
    ) -> None:
        """`status` cannot say "key lost" — it has three values — so the two flags must.

        The temp store this class builds *is* the key-loss shape: ciphertext on disk with no key for it.
        `status` reports `not_initialised`, which is the declared design rather than a second defect, and
        it is why the contract tells a client to read `db_exists` and `key_in_keychain` and not only
        `status`. Asserted so a future simplification of the payload cannot quietly remove the operator's
        only way to tell "initialise me" from "do not dare initialise me".
        """
        payload = client.get("/api/assurance/status").json()

        assert payload["db_exists"] is True, payload
        assert payload["key_in_keychain"] is False, payload
        assert payload["configured"] is False, payload

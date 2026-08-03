"""The capability that gates the assurance modules probes the store the manifest names.

`_inject_capability_sentinels` decides whether the assurance ontology, control-structure, UCA-matrix,
FMEA-matrix and bowtie modules register at all. It asked a literal:
`Path(__file__).resolve().parents[2] / ".arch-assurance" / "store.db"` — the source tree — while every
other consumer asked the deployment manifest: the CLI (`_assurance_commands._default_db_path`), the MCP
read tool (`assurance_mcp.context.default_db_path`), and the REST status route. So a deployment that moved
its store with `ARCH_ASSURANCE_DB_PATH` or a settings key had its *modules* gated on one store's existence
and its *reads* served from another, with nothing to say the two disagreed.

The probe underneath had the same shape twice over: `make_capability` recovered a workspace root from the
db path with `db_path.parent.parent`, and `_sqlcipher_available` then re-derived
`workspace_root / ".arch-assurance" / "store.db"` from it. A moved store was therefore probed at its old
address even if the right path had been handed in.

**Why this matters beyond tidiness.** It is the blocker in front of the fixture *store* — the disposable
confidential store the assurance write walks need. A fixture backend can point the manifest at a temp
store, but until this reads the manifest the capability would still report on the developer's real one:
the modules would register on one store's existence while the process served another, which is the
disagreement class this release keeps finding.

The credential store is redirected in every test below, and the suite redirects it globally as well
(`tests/conftest.py`). Both matter: `accounts.present` is a *read* of a credential backend, and the
point of a capability test is the path it asks about, never the machine's real secrets.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_TREE_STORE = REPO_ROOT / ".arch-assurance" / "store.db"


@pytest.fixture(autouse=True)
def _fresh_manifest_and_capability():
    """Both caches, before and after.

    `make_capability` is `lru_cache`d on its arguments and `resolve_manifest` reads settings each call,
    so a test that changed the environment without clearing would either reuse another test's answer or
    hand its own answer to the next one.
    """
    from src.infrastructure.assurance.capability import make_capability

    make_capability.cache_clear()
    yield
    make_capability.cache_clear()


def _resolved() -> tuple[Path, Path]:
    """What the deployment's sentinel resolved to — the one home both callers now ask."""
    from src.infrastructure.assurance.capability import capability_for_deployment

    capability = capability_for_deployment()
    return capability.db_path, capability.workspace_root


def test_the_store_path_follows_the_manifests_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The load-bearing assertion: `ARCH_ASSURANCE_DB_PATH` moves what the sentinel asks about."""
    moved = tmp_path / "elsewhere" / "assurance.db"
    monkeypatch.setenv("ARCH_ASSURANCE_DB_PATH", str(moved))

    db_path, _workspace = _resolved()

    assert db_path == moved, db_path
    assert db_path != SOURCE_TREE_STORE


def test_without_an_override_it_resolves_where_the_literal_used_to_point(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The compatibility half, and the reason this change is safe under a green suite.

    A deployment that has moved nothing must get the same answer as before, or every developer's
    assurance modules would stop registering on the strength of a refactor.
    """
    monkeypatch.delenv("ARCH_ASSURANCE_DB_PATH", raising=False)

    db_path, workspace = _resolved()

    assert db_path == SOURCE_TREE_STORE, db_path
    # From `assurance_workspace_root()`, which the bundle uses too — not from the manifest. See
    # `test_the_capability_and_the_bundle_resolve_one_workspace_root`.
    assert workspace == REPO_ROOT, workspace


def test_the_probe_asks_about_the_path_it_is_given_rather_than_rederiving_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_sqlcipher_available` used to rebuild `<root>/.arch-assurance/store.db` from a workspace root.

    So a store under any other name or place was reported absent while being perfectly present. Driven
    through `make_capability` rather than the private helper, because the round-trip that lost the path
    was in `make_capability` itself.
    """
    from src.infrastructure.assurance import _credential_accounts as accounts
    from src.infrastructure.assurance.capability import make_capability

    monkeypatch.setenv("ARCH_ASSURANCE_CREDENTIALS_DIR", str(tmp_path / "credentials"))
    moved = tmp_path / "deployment" / "assurance.db"
    moved.parent.mkdir(parents=True)
    moved.write_bytes(b"not a real store; the probe checks presence, not contents")
    # A key *for this path*: presence is scoped, so the probe asking about the wrong path would also be
    # asking about the wrong account.
    accounts.write(accounts.DB_KEY, moved, "deadbeef")

    capability = make_capability(moved, tmp_path / "deployment")

    assert capability.enabled is True


def test_a_store_that_is_not_there_leaves_the_capability_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail-closed, which is the whole point of the sentinel: no store, no assurance modules.

    Asserted with the *key present and the file absent* — the key-loss shape — because that is the case
    where a probe that only checked credentials would wrongly enable the modules and every assurance
    read would then fail at first use instead of the module declining to register.
    """
    from src.infrastructure.assurance import _credential_accounts as accounts
    from src.infrastructure.assurance.capability import make_capability

    monkeypatch.setenv("ARCH_ASSURANCE_CREDENTIALS_DIR", str(tmp_path / "credentials"))
    absent = tmp_path / "deployment" / "assurance.db"
    absent.parent.mkdir(parents=True)
    accounts.write(accounts.DB_KEY, absent, "deadbeef")

    assert make_capability(absent, tmp_path / "deployment").enabled is False


def test_the_capability_and_the_bundle_resolve_one_workspace_root() -> None:
    """The regression this change nearly introduced, asserted so it cannot arrive later.

    The store *path* is the manifest's — the factory opens exactly that file, so
    `ARCH_ASSURANCE_DB_PATH` must move both. The *workspace root* is not: it is what the bundle is keyed
    on, and what locates a `private-git` repository and the hash the credential account name is derived
    from. Taking it from `manifest.workspace_root` was the obvious symmetry and would have been wrong: on
    a deployment with both a deployment root and a private-git backend the manifest says
    `<root>/workspace` while the bundle still uses the source tree, so the capability would have reported
    on a repository nothing opens.

    They agreed by coincidence before, both deriving a source tree. This asserts they agree on purpose.
    """
    from src.infrastructure.assurance.capability import capability_for_deployment
    from src.infrastructure.mcp.assurance_mcp.context import assurance_workspace_root

    assert capability_for_deployment().workspace_root == assurance_workspace_root()


def test_a_deployment_root_does_not_move_the_workspace_out_from_under_the_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The specific configuration that would have diverged: a deployment root plus a moved store.

    `manifest.workspace_root` becomes `<root>/workspace` here, and the store path moves with the
    override — but the workspace the capability probes must stay the bundle's.
    """
    from src.infrastructure.assurance.capability import capability_for_deployment
    from src.infrastructure.mcp.assurance_mcp.context import assurance_workspace_root

    monkeypatch.setenv("ARCH_ASSURANCE_DB_PATH", str(tmp_path / "deploy" / "assurance.db"))

    capability = capability_for_deployment()

    assert capability.db_path == tmp_path / "deploy" / "assurance.db"
    assert capability.workspace_root == assurance_workspace_root()


def test_the_sqlcipher_store_filename_is_never_named_in_code_again() -> None:
    """Named directly so it cannot come back as a "harmless" default beside the manifest read.

    A literal here is not harmless: this is the one path in the product that decides whether a whole
    module class exists, and it disagreed with every other consumer for a release. The behaviour tests
    above catch a literal that *replaces* the manifest; this catches one that joins it.

    **Scoped to `store.db`, and the scope is the finding.** A first version flagged every
    `.arch-assurance` string and caught `.arch-assurance-git` three times — which
    `_private_git_available` derives from the workspace root *because it must*: the deployment manifest
    resolves `assurance_db_path` and `signals_db_path` and has no field for the private-git repository.
    So the same gap exists one size smaller, for a non-default backend, and closing it means adding a
    manifest field with its own resolution rules rather than editing this probe. Recorded rather than
    fixed, and the assertion is honest about which half it covers.

    Parsed rather than grepped. The first version searched the file text and matched the docstring
    explaining the removed literal — a source scan that cannot tell code from prose reports the
    explanation as the offence.
    """
    import ast

    source = (
        REPO_ROOT / "src" / "infrastructure" / "assurance" / "capability.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Docstrings are `Constant` strings as much as code is, and the docstring that *explains* the removed
    # literal quotes it. Collected by identity rather than by heuristic: a docstring is the first
    # statement of a module, class or function, which is a fact about the tree and not a guess about text.
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    offenders = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and "store.db" in node.value
        and id(node) not in docstrings
    ]
    assert offenders == [], (
        "capability.py names the SQLCipher store's filename in code again instead of asking the "
        f"manifest for it: {offenders}"
    )
    assert "resolve_manifest" in source


def test_the_capability_never_reads_the_developers_real_credential_directory() -> None:
    """A guard on this file, not on the product.

    Every test above writes a credential. The suite redirects the directory session-wide, and this
    asserts that redirection is actually in force — a capability test that reached
    `~/.config/arch-assurance` is how this repository lost its store twice.
    """
    from src.infrastructure.assurance._credential_store import _CREDENTIALS_DIR_ENV

    redirected = os.environ.get(_CREDENTIALS_DIR_ENV)
    assert redirected, "the suite's credential redirection is not set; refusing to touch credentials"
    assert not Path(redirected).is_relative_to(Path.home() / ".config" / "arch-assurance")

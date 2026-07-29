"""Architecture/dependency contract for the ingest script: it submits typed
bundles through the IngestSecuritySignals command and NEVER imports a signals
connector (the legacy import_bom/import_vulnerabilities adapters) — the snapshot
lifecycle has exactly one owner."""

from __future__ import annotations

import ast
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "assurance" / "ingest_security_signals.py"

_FORBIDDEN_MODULES = (
    "src.infrastructure.assurance._collocated_signals_connector",
    "src.infrastructure.assurance._security_connector",
)
_FORBIDDEN_NAMES = (
    "SecuritySignalConnector",
    "CollocatedSQLCipherSignalsConnector",
    "SQLiteSecurityConnector",
    "import_bom",
    "import_vulnerabilities",
)


def _all_imports(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def test_script_imports_no_signals_connector() -> None:
    tree = ast.parse(_SCRIPT.read_text(encoding="utf-8"))
    imports = _all_imports(tree)
    offenders = {
        name for name in imports
        if any(name.startswith(forbidden) for forbidden in _FORBIDDEN_MODULES)
        or any(name.endswith(f".{forbidden}") for forbidden in _FORBIDDEN_NAMES)
    }
    assert offenders == set(), f"the ingest script must not touch connectors: {offenders}"


def test_script_never_references_connector_apis_even_lazily() -> None:
    source = _SCRIPT.read_text(encoding="utf-8")
    offenders = [name for name in _FORBIDDEN_NAMES if name in source]
    assert offenders == [], f"connector API references found in the script: {offenders}"


_LIFECYCLE_TRANSITIONS = (
    "create_staging_snapshot",
    "populate_snapshot",
    "complete_snapshot",
    "activate_snapshot",
    "fail_snapshot",
)


_SHARED_ACQUISITION = "src.infrastructure.assurance.signal_sources"
_SHARED_SUBMISSION = "src.infrastructure.assurance.signal_ingest"


def test_script_submits_through_the_shared_ingest_boundary() -> None:
    """The script must SOURCE its bundle and its submission from the shared
    modules, so snapshot-id policy and the single-writer boundary are not
    re-invented per surface.

    Asserted structurally rather than by grepping for a function name: the name
    is an implementation detail that legitimately changes, whereas "the bundle
    and the submission both come from the shared boundary" is the contract.
    """
    tree = ast.parse(_SCRIPT.read_text(encoding="utf-8"))
    imports = _all_imports(tree)

    assert f"{_SHARED_SUBMISSION}.submit_bundle" in imports, (
        "the script must submit through the shared boundary"
    )
    assert any(name.startswith(_SHARED_ACQUISITION) for name in imports), (
        "the script must acquire its bundle through the shared acquisition module"
    )


def test_script_does_not_assemble_its_own_bundle() -> None:
    """Constructing an IngestBundle in the script would duplicate assembly and let
    the two ingest surfaces drift — the failure the shared boundary exists to
    prevent. Importing the type for annotations is fine; instantiating it is not.
    """
    tree = ast.parse(_SCRIPT.read_text(encoding="utf-8"))
    constructed = [
        node.func.id for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "IngestBundle"
    ]
    assert constructed == [], "the script must not build IngestBundle itself"


def test_script_never_drives_lifecycle_transitions_itself() -> None:
    source = _SCRIPT.read_text(encoding="utf-8")
    offenders = [name for name in _LIFECYCLE_TRANSITIONS if name in source]
    assert offenders == [], f"the script must not drive the snapshot lifecycle: {offenders}"

"""Where live security signals come from: SBOM generation and OSV acquisition.

Separated from ``signal_ingest`` deliberately. That module is the SUBMISSION
boundary (assemble a bundle, submit it through the serialised write); this one is
the ACQUISITION side — it shells out to the pinned SBOM generators and queries
OSV. Both the dogfooding script and the ``arch-assurance seed --with-signals``
command need acquisition, so it lives here rather than in either caller.

Adding a target means adding one entry to ``SBOM_TARGETS``; nothing else in the
pipeline knows the target vocabulary.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from src.application.security_signals.bundle_assembly import AcquisitionInputs
from src.application.security_signals.command import IngestResult
from src.application.security_signals.ports import SnapshotStore
from src.infrastructure.assurance.osv_client import OsvClient, OsvComponentQuery
from src.infrastructure.assurance.signal_ingest import assemble_bundle, submit_bundle

#: Generators are trusted local tooling, but they are still subprocesses: bounded
#: time, no shell, and failures surface as CalledProcessError rather than a
#: silently empty BOM (an empty BOM would ingest as "no components", which reads
#: identically to a clean scan).
_SUBPROCESS_TIMEOUT_SECONDS = 600

SbomGenerator = Callable[[Path], "tuple[dict[str, object], dict[str, str]]"]


def _run(command: list[str], *, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, check=True,
        timeout=_SUBPROCESS_TIMEOUT_SECONDS,
    )
    return completed.stdout


def generate_python_sbom(repo_root: Path) -> tuple[dict[str, object], dict[str, str]]:
    """The backend's uv environment via the pinned cyclonedx-py generator.

    ``--pyproject`` is what makes directness classifiable. Without it,
    ``cyclonedx-py environment`` describes an environment with NO
    ``metadata.component``: the dependency graph is still emitted in full, but
    there is no root to measure depth from, so every component classifies as
    "unknown" (measured: 107 unknown vs 18 direct / 71 transitive with the root).
    """
    version = _run(["uv", "run", "cyclonedx-py", "--version"]).strip()
    command = ["uv", "run", "cyclonedx-py", "environment", "--output-format", "JSON"]
    pyproject = repo_root / "pyproject.toml"
    if pyproject.is_file():
        command += ["--pyproject", str(pyproject)]
    else:
        # Degrading silently here would produce an all-"unknown" snapshot that
        # reads exactly like a successful scan.
        print(
            f"warning: {pyproject} not found — the SBOM will have no root component "
            "and every component's directness will be 'unknown'",
            file=sys.stderr,
        )
    raw = _run(command, cwd=repo_root)
    return json.loads(raw), {"generator": "cyclonedx-py", "generator_version": version}


def generate_npm_sbom(repo_root: Path) -> tuple[dict[str, object], dict[str, str]]:
    """The GUI via `npm sbom` (npm >= 9.5) — preserves the dependency graph."""
    version = _run(["npm", "--version"]).strip()
    raw = _run(["npm", "sbom", "--sbom-format", "cyclonedx"], cwd=repo_root / "tools" / "gui")
    return json.loads(raw), {"generator": "npm sbom", "generator_version": version}


SBOM_TARGETS: Mapping[str, SbomGenerator] = {
    "python": generate_python_sbom,
    "npm": generate_npm_sbom,
}


def generate_sbom(target: str, *, repo_root: Path) -> tuple[dict[str, object], dict[str, str]]:
    """Produce a CycloneDX document for one target. Unknown targets are a typed
    error naming the supported set — never a silent empty BOM."""
    generator = SBOM_TARGETS.get(target)
    if generator is None:
        raise ValueError(
            f"unknown SBOM target {target!r}; supported: {', '.join(sorted(SBOM_TARGETS))}"
        )
    return generator(repo_root)


def osv_acquisition(
    queryable: Sequence[Mapping[str, str]], *, base_url: str | None = None,
) -> AcquisitionInputs:
    """Live acquisition: query OSV for every queryable component."""
    client = OsvClient(base_url=base_url) if base_url else OsvClient()
    acquisition = client.query_components([
        OsvComponentQuery(component_id=q["component_id"], purl=q["purl"])
        for q in queryable
    ])
    return AcquisitionInputs(
        vulnerability_ids_by_component=acquisition.vulnerability_ids_by_component,
        vulnerabilities_by_id=acquisition.vulnerabilities_by_id,
        unmatched_components=acquisition.unmatched_components,
        failed_vulnerability_fetches=acquisition.failed_vulnerability_fetches,
    )


def build_live_bundle(
    target: str,
    anchor_entity_id: str,
    *,
    repo_root: Path,
    osv_base_url: str | None = None,
    request_id: str = "",
) -> Any:
    """Generate the target's SBOM, acquire OSV data for it, and return the bundle."""
    sbom_data, generator_metadata = generate_sbom(target, repo_root=repo_root)
    return assemble_bundle(
        anchor_entity_id,
        sbom_data,
        acquire=lambda queryable: osv_acquisition(queryable, base_url=osv_base_url),
        request_id=request_id,
        generator_metadata=generator_metadata,
        source_metadata={"vulnerability_source": "osv.dev"},
    )


def ingest_live_target(
    target: str,
    anchor_entity_id: str,
    *,
    snapshot_store: SnapshotStore,
    repo_root: Path,
    osv_base_url: str | None = None,
    request_id: str = "",
) -> IngestResult:
    """Acquire and submit one target's signals in a single act — the whole live
    ingest, shared by the dogfooding script and the seed command."""
    bundle = build_live_bundle(
        target, anchor_entity_id, repo_root=repo_root,
        osv_base_url=osv_base_url, request_id=request_id,
    )
    return submit_bundle(bundle, snapshot_store=snapshot_store)

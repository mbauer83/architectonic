"""Composition root for the artifact verifier: the application verifier wired to the
infrastructure adapters that give its ports real behaviour.

`ArtifactVerifier` lives in the application layer, which may not import infrastructure, so
its own fallback for the PlantUML syntax port is `_NullPumlSyntax`. That fallback is
correct for the application layer used in isolation and silently wrong everywhere a real
check was expected: `check_puml_syntax` defaults to True, so a verifier built without an
injected port reports a clean syntax result for every diagram without ever looking at one.

Wiring belongs here, once, rather than at each construction site. Per-site injection is
what allowed every production path — GUI, MCP, bulk write and delete, promotion, model
exchange — to run with the switch on and nothing behind it, and it would let the next
construction site regress the same way. `tests/architecture/test_verifier_composition.py`
enforces that infrastructure builds verifiers through this factory.

Cost is bounded by the pieces the syntax checker already provides: `check_puml_syntax=False`
for paths that must not spawn a subprocess at all, batching (one JVM per chunk of files)
for whole-repository verification, and the `ARCH_SKIP_PUML_SYNTAX` environment switch. A
missing `plantuml.jar` degrades to a W350 warning rather than an error.
"""

from __future__ import annotations

from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.verification.verifier_ports import FileInventoryPort
from src.infrastructure.verification.adapters import DefaultPumlSyntaxAdapter


def build_artifact_verifier(
    registry: ArtifactRegistry | None = None,
    *,
    catalogs: RuntimeCatalogs,
    committed_repo: object | None = None,
    file_inventory: FileInventoryPort | None = None,
    check_puml_syntax: bool = True,
) -> ArtifactVerifier:
    """An ArtifactVerifier whose PlantUML syntax port actually runs PlantUML.

    Pass `check_puml_syntax=False` where spawning a subprocess is not acceptable; the port
    is then left unset rather than built, and the verifier skips the check explicitly
    instead of appearing to run one.
    """
    return ArtifactVerifier(
        registry,
        catalogs=catalogs,
        committed_repo=committed_repo,
        file_inventory=file_inventory,
        check_puml_syntax=check_puml_syntax,
        puml_syntax=DefaultPumlSyntaxAdapter() if check_puml_syntax else None,
    )

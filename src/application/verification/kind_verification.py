"""What the verifier is handed for each kind of artifact, and how a file is sent to it.

**The binding is not declared here.** Which verifier a kind has is decided once, at the composition
layer (`src/infrastructure/verification/kind_bindings.py`), beside the verifier's own composition root:
a kind's row in the domain names neither callable, and the readers and verifiers a kind may need live
at more than one layer. This module states the *shape* of a binding, which is the application's to
own, and dispatches on one.

**Dispatch has no fall-through.** It used to: `verify_standalone_artifact` sent an icon to the icon
verifier and *everything else* to the document verifier, so a third standalone kind would have been
verified as a document and passed or failed for reasons that were not its own. Now a file is sent to
the verifier bound to its kind, and a kind with none bound answers `unverified` — a result that is
never counted as passed.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, TypeAlias

from src.application.verification.artifact_verifier_types import VerificationResult
from src.domain.ontology_representation.artifact_types import RepoMount
from src.domain.repository.artifact_location import ArtifactKindName

if TYPE_CHECKING:
    from src.application.verification._verifier_snapshot import RepositorySnapshot
    from src.application.verification.artifact_verifier import ArtifactVerifier


#: Verify one file of the kind, given the verifier that holds the registry and catalogs to do it with.
VerifyOne: TypeAlias = Callable[["ArtifactVerifier", Path, "RepositorySnapshot | None"], VerificationResult]


@dataclass(frozen=True, slots=True)
class KindVerifier:
    """How a file of one kind is verified, and every finding that can say it is wrong."""

    verify: VerifyOne
    #: The codes this verifier's rules emit. Never empty: a verifier that declares no rule checks
    #: nothing, and would pass every file it is handed.
    rule_codes: frozenset[str]


@dataclass(frozen=True, slots=True)
class KindBinding:
    """What one kind of artifact is bound to. `verifier` is None for a kind its row declares unverified."""

    reader: Callable[[Path, list[RepoMount], frozenset[str]], object]
    verifier: KindVerifier | None


#: One binding per kind of the kind table, declared at the composition layer.
KindBindings: TypeAlias = Mapping[ArtifactKindName, KindBinding]


def verify_by_binding(
    bindings: KindBindings,
    host: ArtifactVerifier,
    kind: ArtifactKindName,
    path: Path,
    snapshot: RepositorySnapshot | None = None,
) -> VerificationResult:
    """Verify *path* as a file of *kind* with the verifier bound to it; `unverified` when none is."""
    binding = bindings.get(kind)
    match binding.verifier if binding is not None else None:
        case KindVerifier(verify=verify):
            return verify(host, path, snapshot)
        case None:
            return VerificationResult(path=path, file_type=kind, outcome="unverified")

"""Which verifier each kind of artifact is bound to: one binding per row of the kind table.

The kind table (`src/domain/repository/artifact_location.py`) states a kind's facts and names no
callable — the domain may import only the domain, and what reads and verifies a kind lives above it.
This is where the two meet, once, beside the verifier's composition root: the factory hands these
bindings to every verifier it builds, and the verifier sends a file to the one bound to its kind.

A kind is named here to *bind* it, which is the one thing besides the table that may know a kind by
its name (`tests/architecture/test_nothing_branches_on_an_artifact_kind_name.py`). Nothing branches on
a name: the table below has an entry per kind, and `kind_binding_contradictions` refuses one that is
missing, one for a kind the table does not declare, a verified kind with no verifier, an unverified
kind with one, and a verifier that declares no rule codes. It runs at startup.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from src.application.artifacts.icon_parsing import parse_icon
from src.application.artifacts.mounted_readers import (
    parse_diagram_for_path,
    parse_document_for_path,
    parse_entity_for_path,
    parse_outgoing_for_path,
    parse_scratchpad_for_path,
)
from src.application.verification import (
    _verifier_diagram,
    _verifier_document,
    _verifier_entity,
    _verifier_icon,
    _verifier_outgoing,
    artifact_verifier_syntax,
)
from src.application.verification.kind_verification import KindBinding, KindBindings, KindVerifier, PerKindVerification
from src.domain.repository.artifact_location import ARTIFACT_KINDS, ArtifactKindName, KindDeclaration

if TYPE_CHECKING:
    from src.application.verification._verifier_snapshot import RepositorySnapshot
    from src.application.verification.artifact_verifier_types import VerificationResult


def _diagram(
    host: PerKindVerification, path: Path, snapshot: RepositorySnapshot | None
) -> VerificationResult:
    """A diagram in markdown is a matrix; in PlantUML, everything else. The notation is the suffix."""
    verify = host.verify_matrix_diagram_file if path.suffix == ".md" else host.verify_diagram_file
    return verify(path, snapshot=snapshot)


KIND_BINDINGS: Mapping[ArtifactKindName, KindBinding] = {
    "entity": KindBinding(
        reader=lambda path, mounts, domain_names: parse_entity_for_path(path, mounts, domain_names=domain_names),
        verifier=KindVerifier(
            verify=lambda host, path, snapshot: host.verify_entity_file(path, snapshot=snapshot),
            rule_codes=_verifier_entity.RULE_CODES,
        ),
    ),
    "connection": KindBinding(
        reader=lambda path, mounts, _domain_names: parse_outgoing_for_path(path, mounts),
        verifier=KindVerifier(
            verify=lambda host, path, snapshot: host.verify_connection_file(path, snapshot=snapshot),
            rule_codes=_verifier_outgoing.RULE_CODES,
        ),
    ),
    "diagram": KindBinding(
        reader=lambda path, mounts, _domain_names: parse_diagram_for_path(path, mounts),
        verifier=KindVerifier(
            verify=_diagram, rule_codes=_verifier_diagram.RULE_CODES | artifact_verifier_syntax.RULE_CODES
        ),
    ),
    "document": KindBinding(
        reader=lambda path, mounts, _domain_names: parse_document_for_path(path, mounts),
        verifier=KindVerifier(
            verify=lambda host, path, snapshot: host.verify_document_file(path, snapshot=snapshot),
            rule_codes=_verifier_document.RULE_CODES,
        ),
    ),
    "icon": KindBinding(
        reader=lambda path, _mounts, _domain_names: parse_icon(path),
        verifier=KindVerifier(
            verify=lambda host, path, snapshot: host.verify_icon_file(path, snapshot=snapshot),
            rule_codes=_verifier_icon.RULE_CODES,
        ),
    ),
    # Its link verdicts are about the ontology, not about the file, and nothing verifies the file.
    "scratchpad": KindBinding(
        reader=lambda path, mounts, _domain_names: parse_scratchpad_for_path(path, mounts),
        verifier=None,
    ),
}


def kind_binding_contradictions(
    kinds: tuple[KindDeclaration, ...] = ARTIFACT_KINDS, bindings: KindBindings = KIND_BINDINGS
) -> Iterator[str]:
    """A sentence for every way *bindings* disagrees with the kind table *kinds*."""
    declared = {kind.name for kind in kinds}
    for name in sorted(set(bindings) - declared):
        yield f"The kind bindings bind {name!r}, which the kind table does not declare. Remove the binding."
    for kind in kinds:
        yield from _row_contradictions(kind, bindings.get(kind.name))


def _row_contradictions(kind: KindDeclaration, binding: KindBinding | None) -> Iterator[str]:
    where = "`src/infrastructure/verification/kind_bindings.py`"
    match binding, kind.verification:
        case None, _:
            yield f"The {kind.name} kind has no binding. Bind its verifier, or None if it is unverified, in {where}."
        case KindBinding(reader=reader), _ if not callable(reader):
            yield f"The {kind.name} kind has no reader. Bind its file reader in {where}."  # type: ignore[unreachable]  # runtime wiring
        case KindBinding(verifier=None), "with-the-model" | "standalone":
            yield (
                f"The {kind.name} kind is verified ({kind.verification}) and has no verifier bound. Bind one "
                f"in {where}, or declare the row unverified."
            )
        case KindBinding(verifier=KindVerifier()), "unverified":
            yield (
                f"The {kind.name} kind is declared unverified and has a verifier bound, which nothing would "
                f"run. Declare the row verified, or unbind the verifier in {where}."
            )
        case KindBinding(verifier=KindVerifier(rule_codes=codes)), _ if not codes:
            yield (
                f"The {kind.name} kind's verifier declares no rule codes, so nothing says what it checks. "
                "Declare the codes its rules emit."
            )
        case _:
            return

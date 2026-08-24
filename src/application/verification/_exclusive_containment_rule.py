"""E340 — two wholes claiming one part through a relation that permits only one.

Registered into `_GENERIC_REPOSITORY_CONTRIBUTIONS` on import, the same mechanism as W044 and E335.

ArchiMate 4 defines composition by exclusivity, and says so in the ontology itself: `create_when`
admits a composition when the target is an integral part of the source "and of that whole alone …
no second whole may claim it", and `never_create_when` sends the shared case to aggregation. Nothing
enforced it. A model could assert that one part constitutes two wholes and every pass — incremental
and full — answered zero errors and zero warnings, so five parts sat composed by two wholes each and
verification never said a word. It surfaced when a person asked why a diagram looked wrong.

The rule names no relation. `exclusive_target` is declared on the connection type, because
`relationship_kind` cannot carry this: composition and aggregation are both `containment` and
exclusivity is the whole of the difference. So the rule reads the flag and applies to whatever
declares it — `archimate-composition` and the datatype notation's `dt-composition` today.

It is repository-level rather than per-file because the two wholes are two *files*: each whole
declares the part in its own `outgoing.md`, and neither file is wrong on its own. That is exactly the
shape a per-file verifier cannot see.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.application.artifacts.parsing import parse_outgoing_file
from src.application.repo_path_helpers import all_model_roots

#: `source-entity` files, wherever a model root holds them.
_OUTGOING_GLOB = "**/*.outgoing.md"


def _exclusive_claims(
    repo_root: Path, is_exclusive: Callable[[str], bool]
) -> dict[tuple[str, str], set[str]]:
    """For each (relation, target) an exclusive relation claims, the sources claiming it.

    Read through `parse_outgoing_file`, which owns turning one of these files into connections —
    the arrow grammar and the multiplicity forms are its business, not this rule's.
    """
    claims: dict[tuple[str, str], set[str]] = {}
    for model_root in all_model_roots(repo_root):
        for path in sorted(model_root.glob(_OUTGOING_GLOB)):
            for conn in parse_outgoing_file(path):
                if conn.source and conn.target and is_exclusive(conn.conn_type):
                    claims.setdefault((conn.conn_type, conn.target), set()).add(conn.source)
    return claims


class ExclusiveContainmentContribution:
    """E340: a target claimed by more than one source of a relation that permits one."""

    diagnostic_codes: tuple[str, ...] = ("E340",)

    def run(self, ctx: Any, result: Any) -> None:
        if ctx.catalogs is None:
            return
        from src.application.verification.artifact_verifier_types import Issue, Severity  # noqa: PLC0415

        claims = _exclusive_claims(Path(ctx.location), ctx.catalogs.connections.claims_its_target_exclusively)
        for (conn_type, target) in sorted(claims):
            sources = claims[(conn_type, target)]
            if len(sources) < 2:
                continue
            result.issues.append(
                Issue(
                    Severity.ERROR,
                    "E340",
                    f"'{target}' is claimed by {len(sources)} sources through {conn_type}, which "
                    f"permits one: {', '.join(sorted(sources))}. All but one is the wrong relation.",
                    ctx.location,
                )
            )


_E340_SINGLETON = ExclusiveContainmentContribution()

from src.domain.diagrams.diagram_verification import _GENERIC_REPOSITORY_CONTRIBUTIONS  # noqa: E402

if not any(isinstance(c, ExclusiveContainmentContribution) for c in _GENERIC_REPOSITORY_CONTRIBUTIONS):
    _GENERIC_REPOSITORY_CONTRIBUTIONS.append(_E340_SINGLETON)

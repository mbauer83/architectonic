"""A341 — an ordered sequence whose composed parts have no order between them (advice).

A process is a causally or temporally ordered sequence of behaviour. One composed of two or more
parts with no triggering or flow between any of them says nothing about that order, and is often a
function wearing the wrong type. Often, not always — a checklist process whose steps genuinely run in
any order is a deliberate choice — so this is *advice*: never blocking, presented by the element's
status, and quiet once the element acknowledges it (`accepted-advice`).

The rule names no type. Which types are sequences, which relations compose and which express order
are the ontology's declarations, resolved by `ordered_sequences.SequenceVocabulary`.

It is repository-level for the same reason E340 is: the order lives in the *parts'* `outgoing.md`
files, not in the whole's, so no one file shows it. And it reads those files, as E340 does, rather
than enumerating through the candidate repository: on the `verify_all` path that repository is
point-lookup only and its `list_*` answer `[]` by design, so a rule listing content through it would
be silent in the product and green in any test that handed it a real store. The point lookup it does
use — one element record, for its type, status and acknowledgements — is what that repository serves.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from src.application.artifacts.parsing import parse_outgoing_file
from src.application.repo_path_helpers import all_model_roots
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.relationships.ordered_sequences import (
    Relation,
    SequenceGraph,
    SequenceVocabulary,
    unordered_parts,
)
from src.domain.verification_advice import (
    ACCEPTED_ADVICE_KEY,
    acceptance_for,
    accepted_advice_from_frontmatter,
    advice_issue,
)
from src.domain.verification_findings import Issue

CODE = "A341"

_OUTGOING_GLOB = "**/*.outgoing.md"


def sequence_vocabulary(catalogs: Any) -> SequenceVocabulary:
    """The ontology's sequence vocabulary, from the runtime catalogs."""
    return SequenceVocabulary.from_ontology(
        catalogs.ontology.all_entity_types(),
        catalogs.ontology.all_connection_types(),
        (rule for module in catalogs.module_catalog.all_ontologies().values() for rule in module.derivation_rules),
    )


def _relations_by_source(repo_root: Path) -> Mapping[str, tuple[Relation, ...]]:
    """Every declared relation under every model root, by source. Read through `parse_outgoing_file`,
    which owns the outgoing-file grammar."""
    table: dict[str, list[Relation]] = {}
    for model_root in all_model_roots(repo_root):
        for path in sorted(model_root.glob(_OUTGOING_GLOB)):
            for conn in parse_outgoing_file(path):
                if conn.source and conn.target:
                    table.setdefault(conn.source, []).append(Relation(conn.conn_type, conn.source, conn.target))
    return {source: tuple(relations) for source, relations in table.items()}


def sequence_advice(record: EntityRecord, parts: tuple[str, ...]) -> Issue | None:
    """The A341 finding about *record* with these unordered *parts*, unless it acknowledged A341."""
    accepted = accepted_advice_from_frontmatter(record.extra.get(ACCEPTED_ADVICE_KEY))
    if not parts or acceptance_for(CODE, accepted) is not None:
        return None
    return advice_issue(
        CODE,
        f"'{record.name}' is a {record.artifact_type}, an ordered sequence, but nothing orders its "
        f"{len(parts)} composed parts: {', '.join(parts)}. Relate them by the order they run in, or if "
        "they are grouped by what they do rather than run in sequence, it may be a function. "
        f"If the grouping is deliberate, acknowledge {CODE} with a reason.",
        location=str(record.path),
        artifact_id=record.artifact_id,
        status=record.status,
        parts=parts,
    )


def element_sequence_advice(
    record: EntityRecord | None, graph: SequenceGraph, vocabulary: SequenceVocabulary
) -> Issue | None:
    """A341 about one element record, given the model's relations and types."""
    if record is None or record.artifact_type not in vocabulary.sequence_types:
        return None
    return sequence_advice(record, unordered_parts(record.artifact_id, graph, vocabulary))


def _type_of(candidate: Any) -> Callable[[str], str | None]:
    def type_of(artifact_id: str) -> str | None:
        record = candidate.get_entity(artifact_id)
        return None if record is None else record.artifact_type

    return type_of


class OrderedSequenceContribution:
    """A341: one advice per sequence element whose two or more composed parts nothing orders."""

    diagnostic_codes: tuple[str, ...] = (CODE,)

    def run(self, ctx: Any, result: Any) -> None:
        if ctx.catalogs is None:
            return
        vocabulary = sequence_vocabulary(ctx.catalogs)
        if not vocabulary.sequence_types:
            return
        relations = _relations_by_source(Path(ctx.location))
        candidates = (
            source for source, rels in relations.items()
            if sum(1 for r in rels if r.conn_type in vocabulary.composing) >= 2
        )
        graph = SequenceGraph(outgoing=lambda s: relations.get(s, ()), type_of=_type_of(ctx.candidate))
        findings = (
            element_sequence_advice(ctx.candidate.get_entity(source), graph, vocabulary) for source in candidates
        )
        result.issues.extend(issue for issue in findings if issue is not None)

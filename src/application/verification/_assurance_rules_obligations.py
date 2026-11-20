"""Verifier rules about which rule an obligation comes from.

An obligation states its citation in two attributes, read here through the one module that names
them. The first two rules are about the store alone; the last two compare a citation with the
reference vocabularies and run only when those are handed in — without them there is no question
to ask, which is different from an answer.
"""

from __future__ import annotations

from src.application.verification._assurance_rule_support import attributes_of
from src.application.verification.assurance_findings import (
    OBLIGATION_CITATION_IS_IN_ITS_CURRENT_FORM,
    OBLIGATION_NAMES_ITS_SOURCE,
    OBLIGATION_PROVISION_IS_LISTED_BY_ITS_SOURCE,
    OBLIGATION_SOURCE_HAS_A_REFERENCE_VOCABULARY,
)
from src.application.verification.assurance_issues import AssuranceIssue, AssuranceVerificationResult
from src.domain.assurance.obligation_citation import (
    PROVISION,
    PROVISION_LABEL,
    SOURCE,
    SOURCE_LABEL,
    ObligationCitation,
    ReferenceProvisions,
    citation_of,
    source_key,
    superseded_attributes_in,
)

#: The command that rewrites a store's superseded citations, named in the finding that reports them.
UPGRADE_COMMAND = "arch-repair upgrade --commit"


def _named(names: tuple[str, ...]) -> str:
    return ", ".join(f"`{name}`" for name in names)


def check_names_its_source(node: dict[str, object], result: AssuranceVerificationResult) -> None:
    """An obligation that does not say which rule imposes it."""
    attributes = attributes_of(node)
    citation = citation_of(attributes)
    missing = tuple(
        f"`{name}` ({label.lower()})"
        for name, label, held in (
            (SOURCE, SOURCE_LABEL, citation.source),
            (PROVISION, PROVISION_LABEL, citation.provision),
        )
        if not held
    )
    # A citation still in its former attributes is one finding, not two: the other rule names the
    # fix, and reporting "no source" beside it would send a reader to type what is already there.
    if not missing or superseded_attributes_in(attributes):
        return
    result.issues.append(AssuranceIssue.of(
        OBLIGATION_NAMES_ITS_SOURCE,
        message=f"Obligation does not state its {' or its '.join(missing)}. Set the attribute on the obligation.",
        node_id=str(node["node_id"]),
    ))


def check_citation_is_in_its_current_form(node: dict[str, object], result: AssuranceVerificationResult) -> None:
    """A citation left in the attributes `source` and `provision` replaced."""
    superseded = superseded_attributes_in(attributes_of(node))
    if not superseded:
        return
    result.issues.append(AssuranceIssue.of(
        OBLIGATION_CITATION_IS_IN_ITS_CURRENT_FORM,
        message=(
            f"Obligation holds its citation in {_named(superseded)}, which nothing reads. "
            f"Run `{UPGRADE_COMMAND}` to move it to `{SOURCE}` and `{PROVISION}`, or set those two "
            f"attributes and remove {_named(superseded)}."
        ),
        node_id=str(node["node_id"]),
    ))


def _checkable(node: dict[str, object]) -> ObligationCitation | None:
    """The citation, when it is complete enough to compare with a vocabulary."""
    citation = citation_of(attributes_of(node))
    return citation if citation.source and citation.provision else None


def check_source_has_a_reference_vocabulary(
    node: dict[str, object],
    provisions: ReferenceProvisions,
    result: AssuranceVerificationResult,
) -> None:
    """A source no vocabulary describes: accepted, and said to be unchecked."""
    citation = _checkable(node)
    if citation is None or source_key(citation.source) in provisions:
        return
    result.issues.append(AssuranceIssue.of(
        OBLIGATION_SOURCE_HAS_A_REFERENCE_VOCABULARY,
        message=(
            f"No reference vocabulary describes the source {citation.source!r}, so the provision "
            f"{citation.provision!r} was accepted without being checked. Nothing to do unless the "
            "source is misspelt."
        ),
        node_id=str(node["node_id"]),
    ))


def check_provision_is_listed_by_its_source(
    node: dict[str, object],
    provisions: ReferenceProvisions,
    result: AssuranceVerificationResult,
) -> None:
    """A provision its source's vocabulary does not list."""
    citation = _checkable(node)
    if citation is None:
        return
    listed = provisions.get(source_key(citation.source))
    if listed is None or citation.provision in listed:
        return
    result.issues.append(AssuranceIssue.of(
        OBLIGATION_PROVISION_IS_LISTED_BY_ITS_SOURCE,
        message=(
            f"The reference vocabulary for {citation.source!r} does not list the provision "
            f"{citation.provision!r}. It lists: {', '.join(sorted(listed))}. The vocabulary holds "
            "the source's key provisions rather than all of them, so check the spelling before "
            "treating this as an error."
        ),
        node_id=str(node["node_id"]),
    ))

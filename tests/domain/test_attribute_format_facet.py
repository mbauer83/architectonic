"""A `format` facet is threaded everywhere, or it is a silent weakening.

The specification this implements states the rule the project had learned independently: thread a
new facet through **every** place a schema passes, or through none. A facet the decoder honours and
the validator drops promises something nothing enforces — the same shape as a notation honoured by
one loader of four.

Six places carry `format`, and there is a test for each: the declaration it is read from, the schema
it is compiled into, the validation that enforces it, the descriptor an authoring form renders from,
the merge that carries it across profiles, and the conflict two disagreeing declarations produce.

A seventh test closes the facet's own version of the failure it exists to prevent: a format nothing
enforces is refused where a declaration is first read, rather than compiling into a schema and being
checked by nobody.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.application._startup_schema_policy import validate_attribute_schemata_policy
from src.application.artifacts.schema import attribute_descriptors, validate_against_schema
from src.domain.ontology_representation.format_rules import (
    ENFORCED_FORMATS,
    FORMAT_RULES,
    accepted_forms_phrase,
)
from src.domain.ontology_representation.profile_conflict_resolution import (
    propose_conflict_resolution,
)
from src.domain.ontology_representation.profiles import (
    ProfileAttribute,
    ProfileDefinition,
    attributes_from_mapping,
    compile_profile_schema,
    merge_property_schemas,
)
from src.domain.repository.repo_default_schemata import DEFAULT_SCHEMATA

_URI_SCHEMA = {"type": "object", "properties": {"Tracked by": {"type": "string", "format": "uri"}}}


def test_a_declaration_carries_the_facet() -> None:
    """Place one: `attributes: {format: uri}` reaches the typed declaration."""
    (attribute,) = attributes_from_mapping({"Tracked by": {"type": "string", "format": "uri"}})

    assert attribute.format == "uri"


def test_an_undeclared_format_is_empty_rather_than_absent() -> None:
    """Most attributes declare none, and that has to be an ordinary value rather than a special case."""
    (attribute,) = attributes_from_mapping({"Name": {"type": "string"}})

    assert attribute.format == ""


def test_the_compiled_schema_carries_the_facet() -> None:
    """Place two: what the declaration says reaches the schema every consumer reads."""
    profile = ProfileDefinition(
        slug="s", name="s",
        attributes=(
            ProfileAttribute(name="Tracked by", format="uri"),
            ProfileAttribute(name="Name"),
        ),
    )

    schema = compile_profile_schema(profile)

    assert schema["properties"]["Tracked by"]["format"] == "uri"
    assert "format" not in schema["properties"]["Name"], "an undeclared facet is not emitted"


def test_validation_accepts_an_absolute_reference() -> None:
    """Place three, the ordinary case: a tracker item or a wiki page."""
    assert validate_against_schema({"Tracked by": "https://tracker.example/PROJ-1"}, _URI_SCHEMA) == []


def test_validation_accepts_a_relative_reference_to_an_artifact() -> None:
    """The case the facet exists for, and the reason this is not JSON Schema's `uri`.

    A reference to something this system manages is written the way every other link to it is, and
    that is relative. JSON Schema's `uri` format requires a scheme and would refuse exactly this;
    `uri-reference` is the correct reading, so it is the one enforced.
    """
    reference = "../../../model/motivation/requirement/REQ@1712870400.Po1Qw3.coherent-model.md"

    assert validate_against_schema({"Tracked by": reference}, _URI_SCHEMA) == []


def test_validation_accepts_an_ssh_address_for_a_repository() -> None:
    """`git@github.com:owner/repo.git` is what a source-repository field usually holds.

    It is not a URI — it carries no scheme, and `github.com` cannot be one because a scheme may not
    contain `@` — so it is accepted as its own form. The first version of this check took it only
    by accident, having asked no more than that the value hold no whitespace.
    """
    for address in ("git@github.com:mbauer83/architectonic.git", "ssh://git@github.com/x/y.git"):
        assert validate_against_schema({"Tracked by": address}, _URI_SCHEMA) == [], address


def test_validation_rejects_a_value_that_addresses_nothing() -> None:
    """A facet nothing enforces is a promise nothing keeps."""
    errors = validate_against_schema({"Tracked by": "see the wiki, somewhere"}, _URI_SCHEMA)

    assert errors == [
        "Tracked by: 'see the wiki, somewhere' is not a valid uri "
        f"— expected {accepted_forms_phrase('uri')}"
    ]


def test_the_refusal_says_what_would_have_been_accepted() -> None:
    """Composed from the rule, not restated here: a message and a rule that disagree is defect 10.

    So the assertion is that every term the `uri` rule specifies reaches the author, whatever those
    terms come to be — not that the sentence reads a particular way today.
    """
    (message,) = validate_against_schema({"Tracked by": "askJohn"}, _URI_SCHEMA)

    for term in FORMAT_RULES["uri"].terms:
        assert term in message, message


def test_validation_rejects_a_bare_word_with_no_spaces() -> None:
    """The check has to be about addressing, not about spacing.

    Asking only for the absence of whitespace accepted `askJohn` as readily as a link, which is a
    check in name and none in effect.
    """
    assert validate_against_schema({"Tracked by": "askJohn"}, _URI_SCHEMA)[0].startswith(
        "Tracked by: 'askJohn' is not a valid uri"
    )


def test_validation_ignores_an_unset_value() -> None:
    """An optional attribute nobody filled in is not a malformed reference."""
    assert validate_against_schema({}, _URI_SCHEMA) == []
    assert validate_against_schema({"Tracked by": ""}, _URI_SCHEMA) == []


def test_the_descriptor_an_authoring_form_reads_carries_the_facet() -> None:
    """Place four: the form sees only the descriptor, so a facet stopping short of it cannot be honoured."""
    descriptors = attribute_descriptors(
        {"type": "object", "properties": {
            "Tracked by": {"type": "string", "format": "uri"},
            "Name": {"type": "string"},
        }}
    )

    assert descriptors["Tracked by"]["format"] == "uri"
    assert "format" not in descriptors["Name"]


def test_a_merge_carries_the_facet_across_profiles() -> None:
    """Place five: an attribute contributed by one profile keeps its facet through the merge."""
    merged, conflicts = merge_property_schemas([
        {"properties": {"Tracked by": {"type": "string", "format": "uri"}}},
        {"properties": {"Name": {"type": "string"}}},
    ])

    assert conflicts == []
    assert merged["properties"]["Tracked by"]["format"] == "uri"


def test_two_formats_for_one_attribute_are_a_conflict() -> None:
    """Place six: disagreeing about what a value addresses is not a last-writer-wins difference.

    Two profiles disagreeing here disagree about whether the value may be followed at all, which is
    the same class of disagreement as two types — so it is reported and the later one is dropped,
    exactly as a type clash is.
    """
    merged, conflicts = merge_property_schemas([
        {"properties": {"Ref": {"type": "string", "format": "uri"}}},
        {"properties": {"Ref": {"type": "string", "format": "date-time"}}},
    ])

    assert conflicts == ["Conflicting definitions for attribute 'Ref': format 'uri' vs 'date-time'"]
    assert merged["properties"]["Ref"]["format"] == "uri", "the later definition is dropped"


def test_a_format_conflict_gets_the_same_resolutions_a_type_conflict_gets() -> None:
    """One message shape for both deciding facets, so a second facet brought no second reader."""
    resolution = propose_conflict_resolution(
        "Conflicting definitions for attribute 'Ref': format 'uri' vs 'date-time'",
        bound_profiles=("tracked-thing",),
    )

    assert resolution is not None
    assert resolution.facet == "format"
    assert resolution.attribute == "Ref"
    assert any("Align the format of 'Ref'" in proposal for proposal in resolution.proposals)


def test_a_type_conflict_still_parses_and_says_type() -> None:
    """The generalisation must not have cost the facet it started with."""
    resolution = propose_conflict_resolution(
        "Conflicting definitions for attribute 'Ref': type 'string' vs 'integer'"
    )

    assert resolution is not None
    assert resolution.facet == "type"
    assert any("Align the type of 'Ref'" in proposal for proposal in resolution.proposals)


def test_a_format_nothing_enforces_is_refused_at_startup(tmp_path: Path) -> None:
    """The facet's own failure mode, closed where a declaration is first seen.

    A format no checker recognises compiles into the schema, reaches an authoring form, and is
    validated by nothing — the silent weakening this facet exists to rule out, reintroduced by the
    facet itself. Startup refuses it and names what may be declared instead.
    """
    schemata = tmp_path / ".arch-repo" / "schemata"
    schemata.mkdir(parents=True)
    (schemata / "attributes.requirement.schema.json").write_text(json.dumps({
        "type": "object",
        "properties": {"Contact": {"type": "string", "format": "email"}},
    }))

    errors, _ = validate_attribute_schemata_policy(tmp_path)

    # The register is stated rather than restated: an assertion listing today's formats would fail
    # on the next one added, which is the product working.
    (message,) = errors
    assert "declares format 'email', which nothing enforces" in message
    assert message.endswith(", ".join(sorted(ENFORCED_FORMATS)))


def test_an_enforced_format_passes_startup(tmp_path: Path) -> None:
    """The register is a gate, not a ban: what it names is declarable."""
    schemata = tmp_path / ".arch-repo" / "schemata"
    schemata.mkdir(parents=True)
    (schemata / "attributes.requirement.schema.json").write_text(json.dumps({
        "type": "object",
        "properties": {"Tracked by": {"type": "string", "format": "uri"}},
    }))

    errors, _ = validate_attribute_schemata_policy(tmp_path)

    assert errors == []


class TestAShippedDescriptionCannotContradictTheChecker:
    """Defect 10: a shipped description said `format: uri` was informative only and that any string
    was accepted, months after the checker began refusing values. Nineteen values written in good
    faith were reported invalid by a checker whose own schema had promised the author anything would
    do — and the corrected sentence already existed in a materialised copy, having never reached the
    default it was copied from.

    Equality between a materialised copy and the shipped default is deliberately **not** asserted
    anywhere: `DefaultSchemataEnsureStep` documents a divergent copy as a supported state — "an
    operator's local edit is never overwritten" — so a gate demanding equality would turn any future
    customisation into a build failure. What is asserted instead is the invariant that holds: a
    description saying what a format accepts says it in the rule's own terms.
    """

    def _format_declaring_properties(self) -> list[tuple[str, str, str, str]]:
        found: list[tuple[str, str, str, str]] = []
        for schema_name, schema in DEFAULT_SCHEMATA.items():
            for prop_name, prop in (schema.get("properties") or {}).items():
                declared = str((prop or {}).get("format") or "") if isinstance(prop, dict) else ""
                if declared:
                    found.append((schema_name, prop_name, declared, str(prop.get("description") or "")))
        return found

    def test_the_whole_shipped_set_is_covered_not_a_subset_of_it(self) -> None:
        """The first version of this measurement read nine of twenty-seven keys and reported one
        drifting property from a third of its subject."""
        assert len(DEFAULT_SCHEMATA) > 20
        assert self._format_declaring_properties()

    def test_every_declared_format_is_one_the_checker_runs(self) -> None:
        """A format nothing checks compiles into the schema and is enforced by nothing."""
        for schema_name, prop_name, declared, _ in self._format_declaring_properties():
            assert declared in ENFORCED_FORMATS, f"{schema_name} / {prop_name}: {declared!r}"

    def test_a_description_that_says_what_the_format_accepts_says_it_in_the_rules_terms(self) -> None:
        """Derived, not restated. A description mentioning its format carries the rule's own terms."""
        for schema_name, prop_name, declared, description in self._format_declaring_properties():
            if f"format: {declared}" not in description and declared not in description.lower():
                continue
            where = f"{schema_name} / {prop_name}"
            for term in FORMAT_RULES[declared].terms:
                assert term in description, f"{where}: {description!r} omits {term!r}"

    def test_no_shipped_description_claims_a_format_is_unenforced(self) -> None:
        """The exact false claim, and the shapes it would come back as."""
        disclaimers = (
            "informative only", "runs no format checker", "any string is accepted",
            "not enforced", "no format checker", "not validated",
        )
        for schema_name, prop_name, _, description in self._format_declaring_properties():
            lowered = description.lower()
            for disclaimer in disclaimers:
                assert disclaimer not in lowered, f"{schema_name} / {prop_name}: {disclaimer!r}"

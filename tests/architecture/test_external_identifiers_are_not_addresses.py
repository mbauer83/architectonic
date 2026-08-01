"""An external identifier is data and a filter, never a resource address.

A PURL, a CPE, a BOM reference, a CVE id: each is defined by another standard, each deliberately
carries structure a URL path segment cannot (`pkg:pypi/requests@2.31.0` has two slashes), and the
same package arrives under different ones from different feeds. This system stores them, matches on
them, and addresses its resources by an id of its own.

The distinction is easy to lose by accident rather than by decision — a component arrives with a
`bom_ref`, the `bom_ref` is unique enough, and it becomes the key everything downstream uses. That
is what happened before: `bundle_assembly` called its correlation key `component_identity`, and the
name made the conflation look intentional. So the rule is checked over the whole manifest rather
than left to a reviewer noticing one row.

Recorded in ADR *Resource Addressing: Identity in the Path, Filters in the Query*.
"""

from __future__ import annotations

import re

from src.infrastructure.rest.route_policy import ROUTE_POLICY, path_parameters

#: Parameter names that would mean an external identifier had become an address. Matched on the
#: whole segment name, so `canonical_vulnerability_id` is caught while `component_id` is not.
_EXTERNAL_IDENTIFIER_PARAMETERS = frozenset({
    "purl",
    "package_url",
    "cpe",
    "bom_ref",
    "source_component_id",
    "canonical_component_id",
    "cve",
    "cve_id",
    "ghsa_id",
})

#: `/api/assurance/vulnerabilities/{identifier}/impact` is the one deliberate exception, and it is
#: not an exception to the rule. A vulnerability is not a resource this system owns and mints an id
#: for: it *is* the external identity, resolved through the alias graph that merges CVE, GHSA and
#: PYSEC spellings of one advisory. The route reads "the impact of this identifier", and the
#: response names the canonical id the resolution chose.
_RESOLUTION_ROUTES = frozenset({"assurance_read_vulnerability_impact"})


def test_no_route_addresses_a_resource_by_an_external_identifier() -> None:
    offenders = {
        row.operation_id: sorted(
            set(path_parameters(row.template)) & _EXTERNAL_IDENTIFIER_PARAMETERS
        )
        for row in ROUTE_POLICY
        if row.operation_id not in _RESOLUTION_ROUTES
        and set(path_parameters(row.template)) & _EXTERNAL_IDENTIFIER_PARAMETERS
    }

    assert offenders == {}, (
        "these routes address a resource by an identifier another standard defines; give the "
        f"resource an internal id and filter by the external one instead: {offenders}"
    )


def test_the_addressable_security_component_is_keyed_on_the_internal_id() -> None:
    """The positive half. Rule 1 of the ADR obliges an imported object to be addressable at all —
    a `?purl=` singleton read is not retained on the grounds that the id will not fit in a path."""
    row = next(
        r for r in ROUTE_POLICY
        if r.template == "/api/assurance/security-components/{component_id}"
    )

    assert row.identity_parameters == ("component_id",)
    assert row.resource_kind == "detail"


def test_a_purl_reaches_the_surface_as_a_filter_not_as_an_identity() -> None:
    """The other positive half: preserving the external identifier is the point, not banning it.

    Asserted through the application signature rather than a route template, because that is where
    the two are distinguished — `component_id` selects by this system's id, `purl` by the package's.
    """
    import inspect

    from src.application.security_signals.signals_read import list_active_findings

    parameters = inspect.signature(list_active_findings).parameters
    assert "purl" in parameters, "a PURL must still be usable to scope a collection"
    assert "component_id" in parameters, "and the internal id must be usable for the same scoping"


def test_the_bundle_correlation_key_is_not_called_an_identity() -> None:
    """Naming is the mechanism here. `component_identity` returning whichever of `bom_ref`, `purl`
    or `name` was present is exactly the conflation the ADR resolves, and the name is what made it
    read as a decision rather than a shortcut."""
    from src.application.security_signals import bundle_assembly

    assert not hasattr(bundle_assembly, "component_identity")
    assert hasattr(bundle_assembly, "source_component_ref")

    docstring = bundle_assembly.source_component_ref.__doc__ or ""
    assert "not an identity" in docstring.lower(), (
        "the docstring has to say what this is not; the previous name is why"
    )


def test_no_source_reference_is_documented_as_a_path_segment() -> None:
    """A grammar check over the manifest's own templates: every path parameter is a single segment.

    Cheap, and it catches the shape of the mistake rather than a list of names — a template that
    tried to accept a slash-bearing identifier would have to spell it with a converter or a second
    segment, and both show up here.
    """
    for row in ROUTE_POLICY:
        for segment in row.template.split("/"):
            if segment.startswith("{"):
                assert re.fullmatch(r"\{[a-z_][a-z0-9_]*\}", segment), (
                    f"{row.operation_id}: {segment!r} is not a plain single-segment parameter"
                )

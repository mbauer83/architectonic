"""One judgement about which reads the model generation validates, held across both transports.

REST answers a conditional GET with a 304; MCP calls are JSON-RPC POSTs and get a generation-keyed
memo a layer in. Two mechanisms, correctly — and one judgement about which reads qualify, which was
stated twice: eight ``conditional_read="etag"`` rows in the route-policy manifest and a separate
frozenset of seven tool names, each with its own copy of the rationale.

They had drifted before anything related them, and relating them settled every divergence: three
reads the MCP memo treated as pure are conditional on REST now, two search routes joined them, one
that resembles them is refused because it merges assurance-store hits, and the datatype catalogue was
removed from the MCP memo because module configuration is not what the model generation describes.
Nothing is pending. What this file refuses is a *silent* divergence, not a declared one.

The manifest stays the REST authority — one row per REST operation is what the rest of it rests on —
so the relation is checked rather than the row generated.
"""

from __future__ import annotations

from src.application.read_model_purity import (
    MODEL_PURE_READS,
    cacheable_mcp_tools,
    conditional_rest_templates,
    pending_rest_templates,
)
from src.infrastructure.mcp.artifact_mcp.install_read_cache import CACHEABLE_READ_TOOLS
from src.infrastructure.rest.route_policy import ROUTE_POLICY, SERVED_CONDITIONAL_READ_TEMPLATES


def _manifest_conditional() -> frozenset[str]:
    return frozenset(row.template for row in ROUTE_POLICY if row.conditional_read == "etag")


def test_the_declared_rest_side_is_exactly_what_the_manifest_marks() -> None:
    declared, marked = conditional_rest_templates(), _manifest_conditional()
    assert sorted(marked - declared) == [], (
        "The manifest marks these conditional and `read_model_purity` does not name them. A read "
        "whose validator is the model generation on REST is the same read on MCP; add it to the "
        "table so the two transports classify it once."
    )
    assert sorted(declared - marked) == [], (
        "`read_model_purity` says these should answer a conditional GET and the manifest does not "
        "mark them. Either mark the row or move the entry to `rest_pending` with its reason."
    )


def test_the_mcp_side_is_derived_rather_than_declared() -> None:
    # Identity, not agreement: the frozenset the installer uses *is* the table's answer, so there is
    # no second list that could drift from it.
    assert CACHEABLE_READ_TOOLS == cacheable_mcp_tools()
    assert CACHEABLE_READ_TOOLS != frozenset()


def test_a_read_pending_on_rest_is_not_also_claimed_conditional() -> None:
    # The two sets partition the REST addresses in the table: an address in both would make the
    # first assertion above pass while the manifest disagreed with the recorded reason.
    assert pending_rest_templates() & conditional_rest_templates() == frozenset()


def test_every_pending_entry_states_why_and_names_a_real_route() -> None:
    templates = {row.template for row in ROUTE_POLICY}
    for read in MODEL_PURE_READS:
        if not read.rest_pending:
            continue
        assert len(read.rest_pending.strip()) > 30, read.what
        for template in read.rest_templates:
            assert template in templates, f"{template} is not a served route"
            row = next(r for r in ROUTE_POLICY if r.template == template)
            assert row.conditional_read == "none", (
                f"{template} is recorded as pending but the manifest already marks it conditional; "
                "drop the `rest_pending` reason."
            )


def test_every_declared_rest_template_names_a_real_route() -> None:
    # A stale template would silently drop out of both directions of the first assertion.
    templates = {row.template for row in ROUTE_POLICY}
    for read in MODEL_PURE_READS:
        for template in read.rest_templates:
            assert template in templates, f"{read.what}: {template} is not a served route"


def test_the_table_is_not_empty_on_either_side() -> None:
    # Both assertions above are satisfiable by an empty table; these are what stop that.
    assert len(MODEL_PURE_READS) > 5
    assert len(conditional_rest_templates()) > 5
    assert len(cacheable_mcp_tools()) > 5
    # No floor under the pending set: it is empty as of 0.2.0, and a floor would mean requiring a
    # known divergence to exist. The partition test above is what keeps it honest when it is not.


def test_the_middleware_matches_what_the_manifest_marks() -> None:
    # The consumer end: the conditional-read middleware compiles its templates from the manifest, so
    # a marked row that never reaches it would make this whole agreement decorative.
    assert SERVED_CONDITIONAL_READ_TEMPLATES == _manifest_conditional()

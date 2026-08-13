"""What a read serves, a write accepts back unchanged.

The documented loop on this surface is "read it, edit it, hand it back", and the canvas hands back
the whole document on every save. So the pair that matters is `to_response`, which writes the served
vocabulary, and `from_request_document`, which reads it — asserted here against each other rather
than each against its own fixture, because a fixture cannot notice that one renamed a field the
other never learned.

That is what happened: a frame declares `permits.domains` in the file and is served
`permitted-domains`, the reader knew only the first, and every frame lost its declaration at the
first save. The scratchpad in this repository has no `permits` block left on any of its four frames.

The round trip is stated over what the vocabulary **permits** — a frame declaring domains, document
types and element types — rather than over what the seeded frames happen to declare today, which is
domains alone. The first version of a gate written the other way round passes against the defect.
"""

from __future__ import annotations

import pytest

from src.application.scratchpad.document import to_response
from src.application.scratchpad.requests import from_request_document
from src.domain.modules.module_registry import ModuleRegistry
from src.domain.scratchpad import Area, scratchpad_from_parts
from src.infrastructure.app_bootstrap import build_module_registry

_ID = "SCR@1786300000.a7Kd2p.round-trip"


@pytest.fixture(scope="module")
def module_registry() -> ModuleRegistry:
    """The real registry: the served element types are derived against it, so a stub would make
    the one key this test says is a resolution look like a declaration."""
    return build_module_registry(complete_vocabulary=True)


def _pad(*areas: Area):
    return scratchpad_from_parts(artifact_id=_ID, name="Round trip", areas=list(areas))


def _handed_back(registry: ModuleRegistry, *areas: Area):
    """A scratchpad, read as a client reads it, and sent straight back as a client sends it."""
    served = to_response(_pad(*areas), group="strategy-and-value", registry=registry)
    return from_request_document(
        {key: value for key, value in served.items() if key != "group"}, artifact_id=_ID
    )


class TestAFrameSurvivesBeingHandedBack:
    def test_the_domains_it_declares_survive(self, module_registry: ModuleRegistry) -> None:
        declared = Area(id="strategy", label="Vision & strategy",
                        permitted_domains=("motivation", "strategy"))

        after = _handed_back(module_registry, declared)

        assert after.area("strategy").permitted_domains == ("motivation", "strategy")

    def test_the_document_types_it_declares_survive(self, module_registry: ModuleRegistry) -> None:
        declared = Area(id="enabling", label="Enabling", permitted_document_types=("standard",))

        after = _handed_back(module_registry, declared)

        assert after.area("enabling").permitted_document_types == ("standard",)

    def test_a_frame_declaring_nothing_still_declares_nothing(
        self, module_registry: ModuleRegistry
    ) -> None:
        """An empty `permits` block would be a decision written where there was none."""
        after = _handed_back(module_registry, Area(id="portfolio", label="Portfolio"))

        area = after.area("portfolio")
        assert (area.permitted_domains, area.permitted_element_types) == ((), ())

    def test_the_resolved_element_types_are_read_back_and_dropped(
        self, module_registry: ModuleRegistry
    ) -> None:
        """The one served key that may be a *resolution*: the element types of the declared domains
        against the current ontology. Storing it would freeze an answer that the ontology owns, so a
        frame that means to narrow element types outright declares them in `permits.elements`."""
        declared = Area(id="strategy", label="Vision & strategy",
                        permitted_domains=("motivation",))

        served = to_response(_pad(declared), group="g", registry=module_registry)
        after = _handed_back(module_registry, declared)

        assert served["areas"][0]["permitted-element-types"]
        assert after.area("strategy").permitted_element_types == ()

    def test_an_edited_declaration_wins_over_the_served_one_it_was_read_from(
        self, module_registry: ModuleRegistry
    ) -> None:
        """A client that edits the frame sends the file's own spelling; the served keys beside it
        are what it read a moment ago, and must not overrule what it just changed."""
        served = to_response(
            _pad(Area(id="strategy", label="Vision & strategy", permitted_domains=("motivation",))),
            group="g", registry=module_registry,
        )
        edited = {**served, "areas": [{**served["areas"][0], "permits": {"domains": ["business"]}}]}

        after = from_request_document(
            {key: value for key, value in edited.items() if key != "group"}, artifact_id=_ID
        )

        assert after.area("strategy").permitted_domains == ("business",)

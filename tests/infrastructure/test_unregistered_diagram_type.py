"""A stored diagram may name a type this deployment does not register.

A repository outlives any one deployment's module set. The self-model carries assurance diagrams,
and the assurance module requires the `confidential_store` capability — so on a host without the
store, `bowtie` is a type the catalog holds and the registry does not.

**This is the configuration CI's pytest job runs in, and a local run usually is not.** The store is
initialised only for the e2e job, so a developer whose store is unlocked registers the assurance
module and never meets the branch. It cost a red shard: `_restate_generated_declarations` resolved
the renderer through `get_diagram_type`, whose `KeyError` is correct only where the caller chose the
type from the registry. The refresh walks the whole catalog, so one unreachable renderer errored all
88 of that module's tests, on every diagram, not only the assurance one.

Written against a type no module provides at all rather than against `bowtie`, so it holds the same
whether or not the machine running it has a store — which is the property that was missing.
"""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.diagram_type_registry import all_diagram_types, find_diagram_type, find_renderer
from src.infrastructure.write.artifact_write.diagram_body_preparation import (
    _prepare_diagram_puml_body,
    _restate_generated_declarations,
)

#: A type no module provides — the state `bowtie` is in wherever the confidential store is absent.
_UNREGISTERED = "no-module-provides-this-type"

_BODY = "@startuml\nrectangle \"A\" as A\nrectangle \"B\" as B\nA --> B\n@enduml\n"


def test_the_registry_answers_that_no_module_provides_it() -> None:
    """The precondition: with a type that resolves, the assertions below would be vacuous."""
    assert find_diagram_type(_UNREGISTERED) is None
    assert find_renderer(_UNREGISTERED) is None


def test_a_registered_type_still_answers_with_its_renderer() -> None:
    """The other half — the accessor must not answer None for everything.

    Taken from the registry rather than named here: which types a deployment registers is the
    thing under test, so pinning one would make this fail for the reason it is meant to tolerate.
    """
    registered = next(iter(all_diagram_types()))

    assert find_renderer(registered) is not None


def test_restating_generated_declarations_leaves_the_body_alone(tmp_path: Path) -> None:
    """Absent means untouched: the header the body was stored with is the header it keeps."""
    assert _restate_generated_declarations(_BODY, tmp_path, _UNREGISTERED) == _BODY


def test_preparing_a_body_leaves_its_includes_alone(tmp_path: Path) -> None:
    """No renderer, so no include to inject — and no reason to refuse an edit that carries none."""
    assert _prepare_diagram_puml_body(_BODY, tmp_path, _UNREGISTERED) == _BODY

"""The diagram-type adapter answers for the whole registry, not only for one name at a time.

`diagram_type_registry` exists so its callers never hold the module-registry singleton. It offered
`get_diagram_type` and `find_diagram_type` but no enumeration, so every caller wanting the whole set
reached past it to `get_module_registry()` — the exact coupling the adapter was introduced to
remove. Adding the delegation is the fix; this pins it, and pins that it agrees with the registry it
delegates to rather than building its own answer.
"""

from __future__ import annotations

from src.infrastructure.app_bootstrap import get_module_registry
from src.infrastructure.diagram_type_registry import all_diagram_types, get_diagram_type


def test_the_adapter_enumerates_every_registered_diagram_type() -> None:
    listed = all_diagram_types()

    assert listed, "the registry reported no diagram types at all"
    assert set(listed) == set(get_module_registry().all_diagram_types()), (
        "the adapter's enumeration disagrees with the registry it delegates to"
    )


def test_each_enumerated_name_resolves_through_the_adapter_s_own_lookup() -> None:
    """Regression for the shape the reach-through invited: an enumeration whose keys are not the
    names `get_diagram_type` accepts is worse than none, because it fails at the call site."""
    for name, module in all_diagram_types().items():
        assert get_diagram_type(name) is module, name

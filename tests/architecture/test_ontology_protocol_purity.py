"""Regression: src.domain.ontology_representation.ontology_protocol must not pull in src.infrastructure."""

from __future__ import annotations

import importlib
import sys


def test_ontology_protocol_imports_no_infrastructure() -> None:
    # Capture modules loaded before importing the target.
    before = set(sys.modules)

    # Import fresh by temporarily removing it if cached.
    sys.modules.pop("src.domain.ontology_representation.ontology_protocol", None)
    importlib.import_module("src.domain.ontology_representation.ontology_protocol")

    after = set(sys.modules)
    new_modules = after - before

    infra_modules = [m for m in new_modules if m.startswith("src.infrastructure")]
    assert not infra_modules, (
        "src.domain.ontology_representation.ontology_protocol must not transitively import src.infrastructure. "
        f"Found: {sorted(infra_modules)}"
    )

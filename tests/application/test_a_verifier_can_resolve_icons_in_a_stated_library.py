"""A verifier can be asked to resolve icon references in a stated library, leaving the original as it was."""

from __future__ import annotations

from src.application.verification.artifact_verifier import ArtifactVerifier
from src.infrastructure.app_bootstrap import process_runtime_catalogs


class _Library:
    def get_icon(self, artifact_id: str) -> None:
        return None


def test_the_copy_resolves_in_the_stated_library_and_the_original_does_not() -> None:
    original = ArtifactVerifier(catalogs=process_runtime_catalogs(), check_puml_syntax=False)
    before = original._diagram_rules.icon_library
    library = _Library()

    other = original.with_icon_library(library)

    assert other.icon_library is library and other._diagram_rules.icon_library is library
    assert original.icon_library is None and original._diagram_rules.icon_library is before

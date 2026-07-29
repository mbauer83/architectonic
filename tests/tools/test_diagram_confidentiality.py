"""Tests for assurance diagram source confidentiality routing (TLP-driven)."""

from __future__ import annotations

from pathlib import Path

from src.application.modeling.artifact_write_formatting import format_diagram_puml
from src.infrastructure.write.artifact_write.diagram_confidentiality import (
    ensure_confidential_gitignore,
    is_assurance_diagram_type,
    is_confidential_diagram_source,
)


class TestConfidentialityDecision:
    def test_assurance_type_unclassified_is_confidential(self) -> None:
        # bowtie is an assurance diagram type; unclassified defaults to confidential.
        assert is_assurance_diagram_type("bowtie") is True
        assert is_confidential_diagram_source("bowtie", None) is True

    def test_assurance_type_publishable_tlp_is_not_confidential(self) -> None:
        assert is_confidential_diagram_source("bowtie", "TLP:GREEN") is False
        assert is_confidential_diagram_source("bowtie", "TLP:WHITE") is False

    def test_assurance_type_above_ceiling_is_confidential(self) -> None:
        assert is_confidential_diagram_source("bowtie", "TLP:AMBER") is True
        assert is_confidential_diagram_source("bowtie", "TLP:RED") is True

    def test_non_assurance_type_is_never_gated(self) -> None:
        # Ordinary architecture diagrams are unaffected, even unclassified.
        assert is_assurance_diagram_type("c4-component") is False
        assert is_confidential_diagram_source("c4-component", None) is False
        assert is_confidential_diagram_source("archimate-application", "TLP:RED") is False

    def test_gsn_is_general_unclassified_and_gated_when_assurance_classified(self) -> None:
        assert is_assurance_diagram_type("gsn") is False
        assert is_confidential_diagram_source("gsn", None) is False
        assert is_confidential_diagram_source("gsn", "TLP:GREEN") is False
        assert is_confidential_diagram_source("gsn", "TLP:AMBER") is True
        assert is_confidential_diagram_source("gsn", "TLP:RED") is True


class TestFormatAndGitignore:
    def test_format_emits_tlp_frontmatter_when_set(self) -> None:
        content = format_diagram_puml(
            artifact_id="BOWTIE@1.a.x", diagram_type="bowtie", name="X",
            version="0.1.0", status="draft", last_updated="2026-06-16",
            puml_body="@startuml\n@enduml", tlp="TLP:GREEN",
        )
        assert "tlp: TLP:GREEN" in content

    def test_format_omits_tlp_when_unset(self) -> None:
        content = format_diagram_puml(
            artifact_id="CC@1.a.x", diagram_type="c4-component", name="X",
            version="0.1.0", status="draft", last_updated="2026-06-16",
            puml_body="@startuml\n@enduml",
        )
        assert "tlp:" not in content

    def test_ensure_confidential_gitignore_ignores_all(self, tmp_path: Path) -> None:
        root = tmp_path / "confidential"
        ensure_confidential_gitignore(root)
        gi = root / ".gitignore"
        assert gi.exists()
        assert "*" in gi.read_text()

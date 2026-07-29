"""The configured guidance source: where `arch-import-guidance` reads from when no `--source` is
passed. It is a setting rather than a constant in the CLI so a deployment serving its own guidance
changes one line; these cover the accessor's tolerance of an absent or malformed section, and that
the shipped default is a fetchable https location rather than empty."""

from __future__ import annotations

from unittest.mock import patch
from urllib.parse import urlparse

from src.config.settings import guidance_default_source, load_settings


class TestGuidanceDefaultSource:
    def test_absent_key_in_guidance_section_returns_empty(self) -> None:
        with patch("src.config.settings.load_settings", return_value={"guidance": {}}):
            assert guidance_default_source() == ""

    def test_absent_guidance_section_returns_empty(self) -> None:
        with patch("src.config.settings.load_settings", return_value={}):
            assert guidance_default_source() == ""

    def test_configured_source_is_returned(self) -> None:
        settings = {"guidance": {"default_source": "https://example.invalid/guidance.yaml"}}
        with patch("src.config.settings.load_settings", return_value=settings):
            assert guidance_default_source() == "https://example.invalid/guidance.yaml"

    def test_non_string_value_falls_back_to_empty(self) -> None:
        with patch("src.config.settings.load_settings", return_value={"guidance": {"default_source": 123}}):
            assert guidance_default_source() == ""

    def test_shipped_default_is_an_https_document_url(self) -> None:
        """Asserted as a shape, not a literal: the URL is an operator-editable setting, so pinning
        the exact string would make relocating the published document a test failure. What must hold
        is that the shipped default is fetchable without `--allow-http` and names a document."""
        source = guidance_default_source()
        parsed = urlparse(source)
        assert parsed.scheme == "https", source
        assert parsed.netloc, source
        assert parsed.path.endswith(".yaml"), source

    def test_load_settings_carries_the_configured_source(self) -> None:
        guidance = load_settings()["guidance"]
        assert isinstance(guidance, dict)
        assert guidance["default_source"] == guidance_default_source()

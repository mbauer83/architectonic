"""A sanitised SVG is rebuilt from the allow-list: nothing in it can name a file, a URL or run code."""

from __future__ import annotations

import base64
import re

import pytest

from src.infrastructure.icons.svg_sanitiser import SvgRefusedError, sanitise_svg

SVG = 'xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"'
PNG_STUB = b"\x89PNG-reencoded"


def _reencode(decoded: bytes) -> bytes | None:
    return PNG_STUB if decoded.startswith(b"\x89PNG") or decoded.startswith(b"\xff\xd8") else None


def _clean(body: str) -> tuple[str, tuple[str, ...]]:
    result = sanitise_svg(f"<svg {SVG} viewBox='0 0 10 10'>{body}</svg>".encode(), _reencode)
    return result.markup, result.removed


def _external_references(markup: str) -> list[str]:
    hrefs = re.findall(r'href="([^"]*)"', markup)
    urls = re.findall(r"url\(([^)]*)\)", markup)
    return [h for h in hrefs if not h.startswith(("#", "data:image/png;base64,"))] + [
        u for u in urls if not u.strip("'\" ").startswith("#")
    ]


@pytest.mark.parametrize(
    ("body", "removed_fragment"),
    [
        ("<script>alert(1)</script>", "<script> removed"),
        ("<foreignObject><div xmlns='http://www.w3.org/1999/xhtml'>x</div></foreignObject>", "<foreignObject>"),
        ("<rect width='1' height='1' onload='alert(1)'/>", "event attribute 'onload'"),
        ("<image href='secret.png' width='5' height='5'/>", "outside the document on <image>"),
        ("<image xlink:href='/etc/passwd' width='5' height='5'/>", "outside the document on <image>"),
        ("<image href='file:///etc/passwd'/>", "outside the document on <image>"),
        ("<image href='http://127.0.0.1/x.png'/>", "outside the document on <image>"),
        ("<image href='data:image/svg+xml;base64,PHN2Zz4='/>", "outside the document on <image>"),
        ("<use href='other.svg#logo'/>", "outside the document on <use>"),
        ("<use xlink:href='http://evil/x.svg#a'/>", "outside the document on <use>"),
        ("<rect fill='url(http://evil/x)'/>", "'fill' pointing outside"),
        ("<rect style='fill:url(/etc/passwd);stroke:#000'/>", "style declarations"),
        ("<filter id='f'><feImage href='/etc/passwd'/></filter>", "<filter> removed"),
        ("<a href='javascript:alert(1)'><rect/></a>", "<a> removed"),
    ],
)
def test_each_way_out_is_removed_and_reported(body: str, removed_fragment: str) -> None:
    markup, removed = _clean(body)

    assert _external_references(markup) == []
    assert "script" not in markup.lower() and "onload" not in markup
    assert any(removed_fragment in line for line in removed), removed


def test_a_stylesheet_import_does_not_survive_and_its_class_rules_are_inlined() -> None:
    markup, _ = _clean(
        "<style>@import url(http://evil/x.css); .cls-1{fill:#0078d4} "
        "@media print{.cls-1{fill:url(http://evil)}} .a > .b{fill:red}</style>"
        "<rect class='cls-1' width='1' height='1'/>"
    )

    assert "<style" not in markup and "evil" not in markup
    assert "fill:#0078d4" in markup


def test_an_embedded_raster_is_kept_only_as_the_codec_re_encoded_it() -> None:
    png = base64.b64encode(b"\x89PNG original bytes").decode()
    markup, _ = _clean(f"<image href='data:image/png;base64,{png}' width='5' height='5'/>")

    assert f"data:image/png;base64,{base64.b64encode(PNG_STUB).decode()}" in markup
    assert png not in markup


def test_an_embedded_raster_the_codec_cannot_decode_is_dropped() -> None:
    junk = base64.b64encode(b"GIF89a not a png").decode()
    markup, removed = _clean(f"<image href='data:image/png;base64,{junk}'/>")

    assert "<image" not in markup and removed


def test_a_fragment_reference_and_a_gradient_survive() -> None:
    markup, removed = _clean(
        "<defs><linearGradient id='g'><stop offset='0' stop-color='#0078d4'/></linearGradient>"
        "<symbol id='s'><path d='M0 0h1v1z'/></symbol></defs>"
        "<rect fill='url(#g)' width='1' height='1'/><use href='#s'/>"
    )

    assert "url(#g)" in markup and 'href="#s"' in markup and "linearGradient" in markup
    assert removed == ()


def test_text_is_kept_in_text_elements() -> None:
    markup, _ = _clean("<text x='1' y='5'>Az<tspan>ure</tspan> AKS</text>")

    assert ">Az<tspan>ure</tspan> AKS</text>" in markup


def test_editor_bookkeeping_is_dropped_silently() -> None:
    markup, removed = _clean(
        "<rect xmlns:inkscape='http://www.inkscape.org/namespaces/inkscape' inkscape:label='x' width='1'/>"
        "<title>Logo</title><metadata>rdf</metadata>"
    )

    assert "inkscape" not in markup and "<title" not in markup and removed == ()


@pytest.mark.parametrize(
    "source",
    [
        b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        b'<svg xmlns="http://www.w3.org/2000/svg"><text>&x;</text></svg>',
        b'<!DOCTYPE svg [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><svg xmlns="http://www.w3.org/2000/svg">&b;</svg>',
        b"<svg xmlns='http://www.w3.org/2000/svg'><path d=",
        b"<html><body>not svg</body></html>",
        b"\x89PNG\r\n\x1a\n<svg xmlns='http://www.w3.org/2000/svg'/>",
        b"<svg xmlns='http://www.w3.org/2000/svg'>" + b"<g/>" * 20_001 + b"</svg>",
    ],
    ids=["xxe", "entity-expansion", "truncated", "not-svg", "polyglot-png-header", "too-many-elements"],
)
def test_a_document_that_is_not_a_plain_svg_is_refused(source: bytes) -> None:
    with pytest.raises(SvgRefusedError):
        sanitise_svg(source, _reencode)


def test_an_svg_without_a_namespace_is_read_and_given_one() -> None:
    result = sanitise_svg(b"<svg viewBox='0 0 1 1'><rect width='1' height='1'/></svg>", _reencode)

    assert result.markup.startswith('<svg viewBox="0 0 1 1" xmlns="http://www.w3.org/2000/svg">')

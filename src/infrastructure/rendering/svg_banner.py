"""Burn a classification banner into an SVG document (the D11 stamped export).

The banner is injected as the LAST child of the root ``<svg>`` element so it
paints above the diagram, anchored to the top-left of the viewport. Input is
parsed defensively with defusedxml — the SVG arrives from the browser."""

from __future__ import annotations

from defusedxml import ElementTree as SafeET

_BANNER_HEIGHT = 22


def stamp_svg_banner(svg: str, banner_text: str) -> str:
    """Return the SVG with a banner group prepended to the viewport. Raises
    ``ValueError`` for input that does not parse as a single SVG document."""
    try:
        root = SafeET.fromstring(svg.encode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — one typed failure for callers
        raise ValueError(f"not a valid SVG document: {exc}") from exc
    if not root.tag.endswith("svg"):
        raise ValueError("root element is not <svg>")

    namespace = root.tag[: -len("svg")].strip("{}")
    prefix = f"{{{namespace}}}" if namespace else ""

    import xml.etree.ElementTree as ET  # noqa: PLC0415 — construction only, input parsed safely above

    group = ET.Element(f"{prefix}g", {"id": "classification-banner"})
    rect = ET.SubElement(group, f"{prefix}rect", {
        "x": "0", "y": "0", "width": "100%", "height": str(_BANNER_HEIGHT),
        "fill": "#1e293b", "opacity": "0.92",
    })
    text = ET.SubElement(group, f"{prefix}text", {
        "x": "8", "y": "15", "fill": "#ffffff",
        "font-size": "11", "font-family": "sans-serif",
    })
    text.text = banner_text
    rect.tail = ""
    root.append(group)
    if namespace:
        ET.register_namespace("", namespace)
    return ET.tostring(root, encoding="unicode")

"""What an uploaded SVG may contain once sanitised: the elements, attributes and CSS properties kept.

Named by what is permitted, for the reason the PlantUML body policy is: a list of what is forbidden
is only as good as its author's memory of every way an SVG can run a script or load a file or URL (`<script>`,
`<foreignObject>`, event attributes, `<use href="other.svg#x">`, `<image href="/etc/…">`,
`feImage`, `url(http…)` in a fill, `@import` in a stylesheet, entities). Anything not listed is not
carried into the rebuilt document, and what is listed covers what vendor logo packs draw with: shapes,
paths, text, gradients, clips and masks.

Filters are left out entirely. `feImage` fetches, and the rest carry little a 64 px icon needs.
"""

from __future__ import annotations

import re

SVG_NAMESPACE = "http://www.w3.org/2000/svg"
XLINK_NAMESPACE = "http://www.w3.org/1999/xlink"

KEPT_ELEMENTS = frozenset({
    "svg", "g", "defs", "symbol", "use", "image",
    "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
    "text", "tspan",
    "linearGradient", "radialGradient", "stop", "clipPath", "mask",
})

#: Elements whose content is dropped silently: they describe, they do not draw.
DESCRIPTIVE_ELEMENTS = frozenset({"title", "desc", "metadata"})

#: Presentation and geometry attributes kept on any kept element. `href` is not here: it is kept only
#: where `reference_attribute_is_kept` says so.
KEPT_ATTRIBUTES = frozenset({
    "id", "class", "viewBox", "preserveAspectRatio", "width", "height", "x", "y", "x1", "y1", "x2", "y2",
    "cx", "cy", "r", "rx", "ry", "fx", "fy", "d", "points", "transform", "pathLength",
    "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-opacity", "stroke-linecap",
    "stroke-linejoin", "stroke-miterlimit", "stroke-dasharray", "stroke-dashoffset", "opacity",
    "clip-path", "clip-rule", "clipPathUnits", "mask", "maskUnits", "maskContentUnits",
    "gradientUnits", "gradientTransform", "spreadMethod", "offset", "stop-color", "stop-opacity",
    "color", "display", "visibility", "font-family", "font-size", "font-weight", "font-style",
    "text-anchor", "dominant-baseline", "letter-spacing", "dx", "dy", "style",
})

KEPT_CSS_PROPERTIES = frozenset({
    "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-opacity", "stroke-linecap",
    "stroke-linejoin", "stroke-miterlimit", "stroke-dasharray", "stroke-dashoffset", "opacity",
    "clip-path", "clip-rule", "mask", "stop-color", "stop-opacity", "color", "display", "visibility",
    "font-family", "font-size", "font-weight", "font-style", "text-anchor", "dominant-baseline",
    "letter-spacing",
})

#: A value may use `url()` only to point inside the document: `url(#gradient)`.
_URL_RE = re.compile(r"url\s*\(", re.IGNORECASE)
_FRAGMENT_URL_RE = re.compile(r"url\(\s*['\"]?#[A-Za-z_][\w.-]*['\"]?\s*\)", re.IGNORECASE)
_FRAGMENT_RE = re.compile(r"^#[A-Za-z_][\w.-]*$")


def value_points_only_inside(value: str) -> bool:
    """Whether every `url()` in an attribute or CSS value is a fragment reference."""
    return len(_URL_RE.findall(value)) == len(_FRAGMENT_URL_RE.findall(value))


def is_fragment_reference(value: str) -> bool:
    return bool(_FRAGMENT_RE.match(value.strip()))


#: The embedded rasters an `<image>` may keep; the codec re-encodes each before it is kept.
EMBEDDABLE_RASTER_SUBTYPES = frozenset({"png", "jpeg"})

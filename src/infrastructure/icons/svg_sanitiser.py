"""Rebuild an uploaded SVG from what the allow-list keeps, so it can run no script and load no file or URL.

The input is parsed with defusedxml, which refuses a DTD and so every entity. The output is then
*constructed*, element by element and attribute by attribute, from what `_svg_allow_list` names;
nothing of the input is copied across wholesale. That is the difference from a filter: a filter
passes what it does not recognise, and a construction cannot.

References are where an SVG names a file or URL, so each is decided
explicitly: `<use>` keeps a fragment reference into the document and nothing else; `<image>` keeps
only an embedded PNG or JPEG, and only after the caller's codec has decoded and re-encoded it, so
the bytes that reach the rasteriser were produced here; a `url()` in a paint, clip or mask value
must point inside the document. Everything removed is reported, so the upload dialog can say what
changed before anything is saved.
"""

from __future__ import annotations

import base64
import binascii
import xml.etree.ElementTree as ET  # construction only; input is parsed by defusedxml
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from src.infrastructure.icons._svg_allow_list import (
    DESCRIPTIVE_ELEMENTS,
    KEPT_ATTRIBUTES,
    KEPT_CSS_PROPERTIES,
    KEPT_ELEMENTS,
    SVG_NAMESPACE,
    XLINK_NAMESPACE,
    embedded_raster,
    is_fragment_reference,
    value_points_only_inside,
)
from src.infrastructure.icons._svg_class_styles import class_declarations
from src.infrastructure.icons._svg_extent import UnreadableExtentError, aspect_ratio

#: Bounds the work the rasteriser is handed. A logo is tens to a few thousand elements.
MAX_ELEMENTS = 20_000

#: Decodes an embedded raster and returns it re-encoded as PNG, or None when it does not decode.
RasterReencoder = Callable[[bytes], bytes | None]

_TEXT_BEARING = frozenset({"text", "tspan"})


class SvgRefusedError(ValueError):
    """The upload is not an SVG document this product will draw."""


@dataclass(frozen=True, slots=True)
class SanitisedSvg:
    markup: str
    #: One line per kind of thing removed, e.g. "<script> removed", in first-seen order.
    removed: tuple[str, ...]
    #: Width over height of the declared canvas, so the rasteriser is given both edges.
    aspect_ratio: float


def sanitise_svg(source: bytes, reencode_raster: RasterReencoder) -> SanitisedSvg:
    root = _parse(source)
    if _local_name(root.tag) != "svg" or _namespace(root.tag) not in ("", SVG_NAMESPACE):
        raise SvgRefusedError("the document's root element is not <svg>")
    try:
        ratio = aspect_ratio(root.attrib)
    except UnreadableExtentError as exc:
        raise SvgRefusedError(str(exc)) from exc
    stylesheets = (el.text or "" for el in root.iter() if _local_name(el.tag) == "style")
    builder = _Builder(reencode_raster, class_declarations(stylesheets))
    rebuilt = builder.element(root)
    if rebuilt is None:  # the root itself is always kept; this is unreachable for a valid root
        raise SvgRefusedError("the document has no drawable root")
    rebuilt.set("xmlns", SVG_NAMESPACE)
    return SanitisedSvg(ET.tostring(rebuilt, encoding="unicode"), tuple(builder.removed), ratio)


def _parse(source: bytes) -> ET.Element:
    try:
        root = SafeET.fromstring(source, forbid_dtd=True)
    except DefusedXmlException as exc:
        raise SvgRefusedError(f"the SVG declares a DTD or an entity, which is refused ({type(exc).__name__})") from exc
    except ET.ParseError as exc:
        raise SvgRefusedError(f"the SVG is not well-formed XML: {exc}") from exc
    if sum(1 for _ in root.iter()) > MAX_ELEMENTS:
        raise SvgRefusedError(f"the SVG has more than {MAX_ELEMENTS} elements")
    return root


class _Builder:
    def __init__(self, reencode_raster: RasterReencoder, class_styles: Mapping[str, str]) -> None:
        self._reencode = reencode_raster
        self._class_styles = class_styles
        self.removed: list[str] = []

    def element(self, source: ET.Element) -> ET.Element | None:
        name = _local_name(source.tag)
        if _namespace(source.tag) not in ("", SVG_NAMESPACE):
            return self._omitted(f"<{name}> from another XML namespace removed")
        if name in DESCRIPTIVE_ELEMENTS or name == "style":
            return None  # a stylesheet's class rules are inlined onto the elements that use them
        if name not in KEPT_ELEMENTS:
            return self._omitted(f"<{name}> removed")
        built = ET.Element(name, self._attributes(name, source))
        if name == "image" and "href" not in built.attrib:
            return self._omitted("<image> without an embedded PNG or JPEG removed")
        if name in _TEXT_BEARING:
            built.text = source.text
        for child in source:
            kept = self.element(child)
            if kept is not None:
                if _local_name(child.tag) in _TEXT_BEARING or name in _TEXT_BEARING:
                    kept.tail = child.tail
                built.append(kept)
        return built

    def _attributes(self, element: str, source: ET.Element) -> dict[str, str]:
        kept: dict[str, str] = {}
        inherited = ";".join(
            self._class_styles[name] for name in source.get("class", "").split() if name in self._class_styles
        )
        attributes = dict(source.attrib)
        if inherited:
            attributes["style"] = f"{inherited};{attributes.get('style', '')}"
        for qualified, value in attributes.items():
            name, namespace = _local_name(qualified), _namespace(qualified)
            if name == "href" and namespace in ("", XLINK_NAMESPACE):
                self._reference(element, value, kept)
            elif name.lower().startswith("on"):
                self._drop(f"event attribute '{name}' removed")
            elif namespace or name not in KEPT_ATTRIBUTES:
                continue  # editor bookkeeping (inkscape:, sodipodi:) and unknown presentation: silent
            elif name == "style":
                self._style(value, kept)
            elif value_points_only_inside(value):
                kept[name] = value
            else:
                self._drop(f"'{name}' pointing outside the document removed")
        return kept

    def _reference(self, element: str, value: str, kept: dict[str, str]) -> None:
        if element == "use" and is_fragment_reference(value):
            kept["href"] = value.strip()
        elif element == "image" and (png := self._embedded_png(value)) is not None:
            kept["href"] = f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"
        else:
            self._drop(f"a reference outside the document on <{element}> removed")

    def _embedded_png(self, value: str) -> bytes | None:
        raster = embedded_raster(value)
        if raster is None:
            return None
        try:
            decoded = base64.b64decode("".join(raster[1].split()), validate=True)
        except (binascii.Error, ValueError):
            return None
        return self._reencode(decoded)

    def _style(self, value: str, kept: dict[str, str]) -> None:
        declarations = [part.partition(":") for part in value.split(";") if ":" in part]
        allowed = [
            f"{prop.strip()}:{val.strip()}"
            for prop, _, val in declarations
            if prop.strip() in KEPT_CSS_PROPERTIES and value_points_only_inside(val)
        ]
        if len(allowed) < len(declarations):
            self._drop("style declarations outside the allowed presentation properties removed")
        if allowed:
            kept["style"] = ";".join(allowed)

    def _omitted(self, reason: str) -> ET.Element | None:
        """Record why an element is left out of the rebuilt document; it contributes nothing."""
        self._drop(reason)
        return None

    def _drop(self, reason: str) -> None:
        if reason not in self.removed:
            self.removed.append(reason)


def _local_name(qualified: str) -> str:
    return qualified.rpartition("}")[2]


def _namespace(qualified: str) -> str:
    return qualified[1:].partition("}")[0] if qualified.startswith("{") else ""

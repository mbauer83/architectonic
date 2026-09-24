"""Turn an upload into the stored icon: size-check, sanitise and draw an SVG, or re-encode a raster.

Every refusal leaves here as `IconRefusedError`, so the upload dialog, the MCP tool and the import
CLI report one vocabulary. The size limit is checked on the bytes before anything parses them.
"""

from __future__ import annotations

from src.domain.icons.normalised_icon import IconRefusedError, NormalisedIcon
from src.domain.icons.render_form import MAX_SOURCE_BYTES, SourceFormat
from src.infrastructure.icons.raster_codec import RasterRefusedError, normalise_raster, reencode_embedded
from src.infrastructure.icons.svg_rasteriser import RasteriseFailedError, rasterise_svg
from src.infrastructure.icons.svg_sanitiser import SvgRefusedError, sanitise_svg


def normalise_upload(source: bytes, source_format: SourceFormat) -> NormalisedIcon:
    if len(source) > MAX_SOURCE_BYTES:
        raise IconRefusedError(f"the file is {len(source):,} bytes; an icon may be at most {MAX_SOURCE_BYTES:,}")
    try:
        return _normalised_svg(source) if source_format == "svg" else _normalised_raster(source, source_format)
    except (SvgRefusedError, RasterRefusedError, RasteriseFailedError) as exc:
        raise IconRefusedError(str(exc)) from exc


def _normalised_svg(source: bytes) -> NormalisedIcon:
    sanitised = sanitise_svg(source, reencode_embedded)
    drawn = normalise_raster(rasterise_svg(sanitised.markup, sanitised.aspect_ratio))
    return NormalisedIcon(
        "svg", drawn.png, drawn.width, drawn.height, sanitised.markup, sanitised.removed + drawn.notes
    )


def _normalised_raster(source: bytes, source_format: SourceFormat) -> NormalisedIcon:
    stored = normalise_raster(source)
    return NormalisedIcon(source_format, stored.png, stored.width, stored.height, None, stored.notes)

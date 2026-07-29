"""Convert browser SVG markup to PlantUML-compatible sprite SVG.

archimateGlyphs.json is designed for browsers; PlantUML's Java SVG renderer
has significant limitations.  This module handles the conversion.
"""

from __future__ import annotations

import math
import re

_SPRITE_STROKE = "#252327"
_LINE_HALF_W = 0.65  # half of 1.3 stroke-width — for open-path → rect conversion

_SVG_ELEM_RE = re.compile(
    r"<(?P<tag>circle|path|rect|line|ellipse|polyline|polygon|use)"
    r"(?P<attrs>[^>]*?)"
    r"(?P<close>/?>)"
)
_PATH_CMD_RE = re.compile(r"([MmHhVvLlZzAaCcQqSsTt])([^MmHhVvLlZzAaCcQqSsTt]*)")
_NUM_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")
_SUBPATH_SPLIT_RE = re.compile(r"(?=M)")


def _ensure_attr(attrs: str, name: str, value: str) -> str:
    if f"{name}=" in attrs:
        return attrs
    return f'{attrs} {name}="{value}"'


def _parse_path_segments(d: str) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    segs: list[tuple[tuple[float, float], tuple[float, float]]] = []
    cx = cy = 0.0
    for cmd, raw in _PATH_CMD_RE.findall(d):
        vals = [float(v) for v in _NUM_RE.findall(raw)]
        if cmd == "M":
            pairs = [(vals[i], vals[i + 1]) for i in range(0, len(vals) - 1, 2)]
            if pairs:
                cx, cy = pairs[0]
                for x2, y2 in pairs[1:]:
                    segs.append(((cx, cy), (x2, y2)))
                    cx, cy = x2, y2
        elif cmd == "m":
            pairs = [(vals[i], vals[i + 1]) for i in range(0, len(vals) - 1, 2)]
            if pairs:
                cx, cy = cx + pairs[0][0], cy + pairs[0][1]
                for dx, dy in pairs[1:]:
                    x2, y2 = cx + dx, cy + dy
                    segs.append(((cx, cy), (x2, y2)))
                    cx, cy = x2, y2
        elif cmd == "H":
            for x2 in vals:
                segs.append(((cx, cy), (x2, cy)))
                cx = x2
        elif cmd == "h":
            for dx in vals:
                x2 = cx + dx
                segs.append(((cx, cy), (x2, cy)))
                cx = x2
        elif cmd == "V":
            for y2 in vals:
                segs.append(((cx, cy), (cx, y2)))
                cy = y2
        elif cmd == "v":
            for dy in vals:
                y2 = cy + dy
                segs.append(((cx, cy), (cx, y2)))
                cy = y2
        elif cmd in ("L", "l"):
            rel = cmd == "l"
            for i in range(0, len(vals) - 1, 2):
                x2 = cx + vals[i] if rel else vals[i]
                y2 = cy + vals[i + 1] if rel else vals[i + 1]
                segs.append(((cx, cy), (x2, y2)))
                cx, cy = x2, y2
    return segs


def _seg_to_path(p1: tuple[float, float], p2: tuple[float, float]) -> str | None:
    x1, y1 = p1
    x2, y2 = p2
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 0.2:
        return None
    hw = _LINE_HALF_W
    if abs(dy) < 0.05:
        xm = min(x1, x2)
        return f'<path d="M{xm:.2f} {y1 - hw:.2f}h{length:.2f}v{hw * 2:.2f}H{xm:.2f}z" fill="{_SPRITE_STROKE}"/>'
    if abs(dx) < 0.05:
        ym = min(y1, y2)
        return f'<path d="M{x1 - hw:.2f} {ym:.2f}v{length:.2f}h{hw * 2:.2f}V{ym:.2f}z" fill="{_SPRITE_STROKE}"/>'
    nx, ny = (-dy / length) * hw, (dx / length) * hw
    ax, ay = x1 + nx, y1 + ny
    bx, by = x1 - nx, y1 - ny
    cx2, cy2 = x2 - nx, y2 - ny
    ex, ey = x2 + nx, y2 + ny
    return (
        f'<path d="M{ax:.2f} {ay:.2f}L{bx:.2f} {by:.2f}L{cx2:.2f} {cy2:.2f}L{ex:.2f} {ey:.2f}z"'
        f' fill="{_SPRITE_STROKE}"/>'
    )


def _open_path_to_elements(d: str) -> str:
    sub_paths = [s for s in _SUBPATH_SPLIT_RE.split(d) if s.strip()]
    if len(sub_paths) > 1:
        return "".join(_open_path_to_elements(sub) for sub in sub_paths)
    segs = _parse_path_segments(d)
    if not segs:
        return ""
    all_aligned = all(abs(s[0][0] - s[1][0]) < 0.05 or abs(s[0][1] - s[1][1]) < 0.05 for s in segs)
    if all_aligned and len(segs) >= 2:
        sx, sy = segs[0][0]
        ex, ey = segs[-1][1]
        all_x = [p[0] for s in segs for p in s]
        all_y = [p[1] for s in segs for p in s]
        x_min, x_max = min(all_x), max(all_x)
        y_min, y_max = min(all_y), max(all_y)
        w, h = x_max - x_min, y_max - y_min
        if w > 0.5 and h > 0.5 and (abs(sy - ey) < 0.1 or abs(sx - ex) < 0.1):
            return f'<path d="M{x_min:.2f} {y_min:.2f}h{w:.2f}v{h:.2f}H{x_min:.2f}z" fill="{_SPRITE_STROKE}"/>'
    return "".join(r for s in segs if (r := _seg_to_path(*s)))


def _rect_to_outline_paths(attrs: str) -> str:
    x_m = re.search(r'\bx="([^"]*)"', attrs)
    y_m = re.search(r'\by="([^"]*)"', attrs)
    w_m = re.search(r'\bwidth="([^"]*)"', attrs)
    h_m = re.search(r'\bheight="([^"]*)"', attrs)
    if not (x_m and y_m and w_m and h_m):
        return ""
    x = float(x_m.group(1))
    y = float(y_m.group(1))
    w = float(w_m.group(1))
    h = float(h_m.group(1))
    t = _LINE_HALF_W * 2
    parts = [
        f'<path d="M{x:.2f} {y:.2f}h{w:.2f}v{t:.2f}H{x:.2f}z" fill="{_SPRITE_STROKE}"/>',
        f'<path d="M{x:.2f} {y + h - t:.2f}h{w:.2f}v{t:.2f}H{x:.2f}z" fill="{_SPRITE_STROKE}"/>',
    ]
    inner_h = h - 2 * t
    if inner_h > 0.1:
        parts.append(f'<path d="M{x:.2f} {y + t:.2f}v{inner_h:.2f}h{t:.2f}V{y + t:.2f}z" fill="{_SPRITE_STROKE}"/>')
        parts.append(
            f'<path d="M{x + w - t:.2f} {y + t:.2f}v{inner_h:.2f}h{t:.2f}V{y + t:.2f}z" fill="{_SPRITE_STROKE}"/>'
        )
    return "".join(parts)


def browser_markup_to_plantuml_svg(markup: str) -> str:
    """Convert browser SVG markup to PlantUML-compatible sprite SVG."""
    markup = markup.replace('fill="currentColor"', f'fill="{_SPRITE_STROKE}"')

    def _patch(m: re.Match) -> str:
        tag = m.group("tag")
        attrs = m.group("attrs")
        close = m.group("close")
        if tag == "path":
            d_val = (re.search(r'\bd="([^"]*)"', attrs) or type("", (), {"group": lambda *_: ""})()).group(1)
            if re.search(r"[Zz]", d_val):
                attrs = _ensure_attr(_ensure_attr(attrs, "fill", _SPRITE_STROKE), "stroke", "none")
                return f"<{tag}{attrs}{close}"
            return _open_path_to_elements(d_val)
        if tag == "rect":
            return _rect_to_outline_paths(attrs)
        attrs = _ensure_attr(
            _ensure_attr(_ensure_attr(attrs, "fill", "none"), "stroke", _SPRITE_STROKE),
            "stroke-width",
            "1.3",
        )
        return f"<{tag}{attrs}{close}"

    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">{_SVG_ELEM_RE.sub(_patch, markup)}</svg>'

"""Orthogonal connector routing: Wybrow, Marriott and Stuckey, "Orthogonal Connector Routing" (GD 2009).

Three stages, as the paper has them, with this product's readability rules built into the first two
rather than patched on after:

1. **An orthogonal visibility graph** over the obstacles (`graph`, `visibility`): segments through
   the corners of every obstacle and every connector's stub ends, each running only as far as the
   first obstacle lets it, with a node where two cross. Elements, text regions and the boxes a
   connector has no end in are obstacles; a box it has an end in is crossed at right angles and never
   run along.
2. **A\\* per connector** (`search`) over (node, direction), costing length plus a penalty per bend.
   Every port leaves by a mandatory straight stub (`ports`): an end that carries a decoration by
   `END_RUN`, any other by `STUB`, so no bend can sit at or behind a decoration.
3. **Nudging** (`nudging`): runs that share a line, or lie along a box border, are separated by an
   ordering and a per-axis placement inside their free space.

`router` runs the three over a scene. Mirrored in `tools/gui/src/domain/layout/routing/`; the two
are held equal by `tests/fixtures/layout_geometry/routing.json`, which both are tested against.
Arithmetic is kept to what the two languages agree on: whole-number lines, sums, comparisons, and
the one rounding both share.
"""

"""The geometry of a diagram's picture: where its shapes sit, as values the domain computes with.

`geometry` holds points, extents and courses; `rendered_picture` what a rendered picture draws, read
off it by `src.infrastructure.rendering.layout`; `box_aliases` the names the renderer gives the boxes
it computes; `picture_checks` what a picture's geometry decides without anybody looking at it.

`layout_block` is the layout a diagram may state; `orthogonal` the course a stated route runs once
completed at right angles; `attachment` what a route owes the elements it joins and how it is kept
when one moves; `layout_checks` what a stated layout gets wrong.
"""

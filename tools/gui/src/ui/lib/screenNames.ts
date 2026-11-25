import type { Extent, Point } from '../../domain/layout/geometry'
import { encloses, heightOf, overlaps, widthOf } from '../../domain/layout/geometry'
import type { OverviewMark } from './diagramOverview'

/**
 * The names written at screen size over a picture whose own text is too small to read (04·1, 04·6).
 *
 * With a reading, its elements are named, above each, the selection first: the rest of the picture is
 * dimmed, and naming it would bury the reading. Without one, the boxes in the window are named, on each,
 * largest first. Either way a name that would cover one already written, or run out of the window, is left
 * out: a wall of overlapping labels says nothing, and the panel's lists name every element.
 */

/** Text smaller than this on screen is not read; under it, names are written. */
export const LEGIBLE_PIXELS = 6
/** More than this many names is a wall of labels, not help: the panel's lists name the rest. */
const MOST = 40
/** A written name's room on screen: its widest, and its height. */
const NAME = { widest: 220, height: 19, perCharacter: 6.6, padding: 14 }

/** One name to write, at a point in the window, above that point or centred on it. */
export interface ScreenName {
  readonly id: string
  readonly name: string
  readonly at: Point
  readonly selected: boolean
  readonly place: 'above' | 'on'
}

/** Where a name of *text* centred at *at* takes room in the window. */
const roomOf = (text: string, at: Point, place: ScreenName['place']): Extent => {
  const width = Math.min(text.length * NAME.perCharacter + NAME.padding, NAME.widest)
  const top = place === 'above' ? at.y - NAME.height - 4 : at.y - NAME.height / 2
  return { left: at.x - width / 2, top, right: at.x + width / 2, bottom: top + NAME.height }
}

/** Where a mark's name is written: above its top edge, or on its centre. */
const anchorOf = (mark: OverviewMark, place: ScreenName['place']): Point => ({
  x: (mark.extent.left + mark.extent.right) / 2,
  y: place === 'above' ? mark.extent.top : (mark.extent.top + mark.extent.bottom) / 2,
})

/**
 * *marks* named in the order given, *place*d, each wholly in *window* (window pixels) and none over another
 * written before it: the first in the order win the room.
 */
const placed = (
  marks: readonly OverviewMark[], place: ScreenName['place'], toWindow: (point: Point) => Point, window: Extent,
): ScreenName[] => {
  const written: ScreenName[] = []
  const taken: Extent[] = []
  for (const mark of marks) {
    if (written.length >= MOST) break
    const name = mark.name ?? mark.id
    const at = toWindow(anchorOf(mark, place))
    const room = roomOf(name, at, place)
    if (!encloses(window, room) || taken.some((other) => overlaps(room, other))) continue
    taken.push(room)
    written.push({ id: mark.id, name, at, selected: mark.selected, place })
  }
  return written
}

const areaOf = (mark: OverviewMark): number => widthOf(mark.extent) * heightOf(mark.extent)

/**
 * The names to write over a picture: none while its text reads (*textPixels*, its text's size on screen,
 * at or above `LEGIBLE_PIXELS`, or unknown); else the reading's, or failing one, the boxes' in view.
 */
export const screenNamesOf = (options: {
  readonly reading: readonly OverviewMark[]
  readonly boxes: readonly OverviewMark[]
  readonly textPixels: number | null
  readonly toWindow: (point: Point) => Point
  readonly window: { readonly width: number; readonly height: number }
}): ScreenName[] => {
  const { reading, boxes, textPixels, toWindow, window } = options
  if (textPixels === null || textPixels >= LEGIBLE_PIXELS) return []
  const room = { left: 0, top: 0, right: window.width, bottom: window.height }
  return reading.length > 0
    // The selection first: it is what the reading is of.
    ? placed([...reading].sort((one, other) => Number(other.selected) - Number(one.selected)), 'above', toWindow, room)
    : placed([...boxes].sort((one, other) => areaOf(other) - areaOf(one)), 'on', toWindow, room)
}

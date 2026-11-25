import type { Extent } from '../../domain/layout/geometry'
import { heightOf, widthOf } from '../../domain/layout/geometry'

/**
 * How a diagram window frames its picture when it opens, and when the reader asks for the whole of it.
 *
 * Three framings, by how far the whole picture would have to shrink to fit the window:
 * - it fits at half its size or more: the whole picture, centred;
 * - it fits only between 35 % and half its size: fitted to the window's width at up to its natural
 *   size, top aligned, the rest reached by panning — a squeezed strip reads worse than a pan;
 * - it fits only below 35 % (owner, Q19): at 60 % on its top-left corner, where its first box is, and
 *   the overview shows where the window is. Fitted, such a picture is specks with no word readable.
 */

/** A whole-picture fit below this is a large diagram: it opens at `LARGE_OPENING` instead (Q19, Q22). */
export const LARGE_BELOW = 0.35
/** The scale a large diagram opens at: its text at a size that reads. */
export const LARGE_OPENING = 0.6
/** Below this whole-picture fit, a picture is fitted to the window's width rather than squeezed. */
const LEGIBLE_MIN_SCALE = 0.5

/** The scale and the offset of the picture's origin in the window, in window pixels. */
export interface Framing {
  readonly scale: number
  readonly tx: number
  readonly ty: number
}

/** The window's room: its size, less what is kept clear along its edges. */
interface Room {
  readonly width: number
  readonly height: number
  readonly side: number
  readonly top: number
  readonly bottom: number
}

const roomOf = (window: { width: number; height: number }): Room => {
  const side = 24
  const top = Math.min(Math.max(window.height * 0.035, 16), 40)
  const bottom = 24
  return {
    width: Math.max(window.width - side * 2, 80), height: Math.max(window.height - top - bottom, 80), side, top, bottom,
  }
}

/** The scale at which the whole of *content* fits a window of *window*'s size. */
export const wholeScaleOf = (content: Extent, window: { width: number; height: number }): number => {
  const room = roomOf(window)
  return Math.min(room.width / widthOf(content), room.height / heightOf(content))
}

/** *content* at *scale*, centred across the window where it is narrower, and from the window's top. */
const framedAt = (content: Extent, window: { width: number }, room: Room, scale: number, left: 'centre' | 'side') => ({
  scale,
  tx: (left === 'centre' || widthOf(content) * scale <= room.width
    ? (window.width - widthOf(content) * scale) / 2 : room.side) - content.left * scale,
  ty: room.top - content.top * scale,
})

/**
 * The whole of *content* in the window: what *Fit the diagram* shows. Where the window opens on the whole
 * picture, that framing; else the picture centred both ways, so a zoom about the window's centre zooms
 * into the picture rather than past it.
 */
export const wholeFramingOf = (content: Extent, window: { width: number; height: number }): Framing | null => {
  const scale = wholeScaleOf(content, window)
  if (!Number.isFinite(scale) || scale <= 0) return null
  if (scale >= LEGIBLE_MIN_SCALE) return openingFramingOf(content, window)
  const room = roomOf(window)
  return {
    ...framedAt(content, window, room, scale, 'centre'),
    ty: room.top + (room.height - heightOf(content) * scale) / 2 - content.top * scale,
  }
}

/** What a window of *window*'s size opens on for *content* (see the module's three framings). */
export const openingFramingOf = (content: Extent, window: { width: number; height: number }): Framing | null => {
  const whole = wholeScaleOf(content, window)
  if (!Number.isFinite(whole) || whole <= 0) return null
  const room = roomOf(window)
  if (whole < LARGE_BELOW) return framedAt(content, window, room, LARGE_OPENING, 'side')
  const scale = whole >= LEGIBLE_MIN_SCALE ? whole : Math.min(room.width / widthOf(content), 1)
  return framedAt(content, window, room, scale, 'centre')
}

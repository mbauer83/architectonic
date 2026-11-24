import type { Extent } from '../../domain/layout/geometry'
import { heightOf, unionOf, widthOf } from '../../domain/layout/geometry'

/**
 * The overview of a diagram (D13, owner Q20 and F10): a small copy of the whole picture with the
 * window drawn on it, shown while part of the picture is outside the window.
 *
 * Its shape follows the picture's. A picture wider than 4 : 1 gets a strip along the bottom of the
 * canvas, because a corner map of a 9 : 1 picture is a sliver 24 px high; any other picture gets a
 * map in the bottom right corner. Both keep the picture's aspect, so a point on the overview is the
 * same point on the picture.
 */

/** Where an element the overview marks is drawn, and whether it is selected or only reached. */
export interface OverviewMark {
  readonly id: string
  readonly extent: Extent
  readonly selected: boolean
  /** The element's name, for the names written at screen size over a small picture (04·6). */
  readonly name?: string
}

/** The part of the picture the marks cover: what `F` frames. Null where nothing is marked. */
export const extentOfMarks = (marks: readonly OverviewMark[]): Extent | null =>
  (marks.length > 0 ? unionOf(marks.map((mark) => mark.extent)) : null)

export interface OverviewShape {
  readonly kind: 'strip' | 'corner'
  readonly width: number
  readonly height: number
}

/** Wider than this, a picture is shown as a strip. */
const STRIP_ASPECT = 4
/** The strip's room, and its gutter from the canvas's sides; the corner map's room. */
const STRIP = { width: 900, minHeight: 34, maxHeight: 96, gutter: 24 }
const CORNER = { width: 220, height: 140, min: 60 }

/** The overview's shape and size for *picture* in a canvas *canvasWidth* pixels wide. */
export const overviewShapeOf = (picture: Extent, canvasWidth: number): OverviewShape => {
  const aspect = widthOf(picture) / Math.max(heightOf(picture), 1)
  if (aspect > STRIP_ASPECT) {
    const room = Math.max(Math.min(canvasWidth - STRIP.gutter, STRIP.width), STRIP.minHeight)
    const height = Math.min(Math.max(room / aspect, STRIP.minHeight), STRIP.maxHeight)
    return { kind: 'strip', width: Math.round(Math.min(room, height * aspect)), height: Math.round(height) }
  }
  // The largest box of the picture's aspect within the corner's room; only a picture far taller than
  // wide is given more width than its aspect would, so it is not a sliver either.
  const width = Math.max(Math.min(CORNER.width, CORNER.height * aspect), CORNER.min)
  const height = Math.max(Math.min(CORNER.height, CORNER.width / aspect), CORNER.min)
  return { kind: 'corner', width: Math.round(width), height: Math.round(height) }
}

/** Whether the window shows the whole picture, when the overview has nothing to tell. */
export const windowShowsAll = (window: Extent, picture: Extent): boolean =>
  window.left <= picture.left + 1 && window.top <= picture.top + 1
  && window.right >= picture.right - 1 && window.bottom >= picture.bottom - 1

/**
 * A mark at a size that survives the overview's scale: never smaller than *least* picture units each
 * way, centred where the element is.
 */
export const markExtent = (extent: Extent, least: number): Extent => {
  const width = Math.max(widthOf(extent), least)
  const height = Math.max(heightOf(extent), least)
  const x = (extent.left + extent.right) / 2
  const y = (extent.top + extent.bottom) / 2
  return { left: x - width / 2, top: y - height / 2, right: x + width / 2, bottom: y + height / 2 }
}

/** What a picture draws: a canvas's own marked drawing where it names one, else every drawn child. */
const DRAWING = '[data-picture-drawing]'
const NOT_DRAWN = new Set(['defs', 'style', 'title', 'desc', 'script', 'metadata'])

/** The attributes a copy may not keep: they name, focus or announce what the picture itself does. */
const isPictureOwn = (name: string): boolean =>
  name === 'id' || name === 'tabindex' || name === 'role' || name.startsWith('aria-')
  || (name.startsWith('data-') && !name.startsWith('data-v-'))

/**
 * A still copy of what *svg* draws, for the overview to show: nothing in it can be focused, found by
 * the picture's selectors or announced, so the overview is a picture and nothing more. The copy
 * keeps its classes and the scope a component styled it with, so it looks as the picture does.
 */
export const drawingCopyOf = (svg: SVGSVGElement): Element[] => {
  const marked = [...svg.querySelectorAll(`:scope > ${DRAWING}`)]
  const parts = marked.length > 0 ? marked
    : [...svg.children].filter((child) => !NOT_DRAWN.has(child.tagName.toLowerCase()))
  return parts.map((part) => {
    const copy = part.cloneNode(true) as Element
    for (const element of [copy, ...copy.querySelectorAll('*')]) {
      for (const name of element.getAttributeNames()) if (isPictureOwn(name)) element.removeAttribute(name)
    }
    return copy
  })
}

/** The picture's own coordinate box, its `viewBox`; null where it states none. */
export const pictureBoxOf = (svg: SVGSVGElement): Extent | null => {
  const box = svg.viewBox?.baseVal
  if (!box || box.width <= 0 || box.height <= 0) return null
  return { left: box.x, top: box.y, right: box.x + box.width, bottom: box.y + box.height }
}

/** Each picture's text size, read once: a picture is replaced, never restyled, when it changes. */
const textSizes = new WeakMap<SVGSVGElement, number | null>()

/**
 * The size the picture writes its text at, in its own units: the middle of its texts' stated sizes,
 * so a title or a footnote does not decide it. Null for a picture with no sized text.
 */
export const pictureTextSizeOf = (svg: SVGSVGElement): number | null => {
  if (textSizes.has(svg)) return textSizes.get(svg) ?? null
  const sizes = [...svg.querySelectorAll('text[font-size]')]
    .map((text) => Number.parseFloat(text.getAttribute('font-size') ?? ''))
    .filter((size) => Number.isFinite(size) && size > 0)
    .sort((one, other) => one - other)
  const size = sizes.length > 0 ? sizes[Math.floor(sizes.length / 2)] : null
  textSizes.set(svg, size)
  return size
}

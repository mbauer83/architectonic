// Names written at screen size while the picture's text is too small to read (04·1, 04·6).
import { describe, expect, it } from 'vitest'
import type { OverviewMark } from './diagramOverview'
import { LEGIBLE_PIXELS, screenNamesOf } from './screenNames'

const mark = (id: string, left: number, top: number, width: number, height: number, selected = false): OverviewMark =>
  ({ id, name: `Name of ${id}`, selected, extent: { left, top, right: left + width, bottom: top + height } })
const identity = (point: { x: number; y: number }) => point
const WINDOW = { width: 1000, height: 600 }

describe('names at screen size', () => {
  it('writes none while the picture\'s own text reads, or where its size is unknown', () => {
    const boxes = [mark('a', 100, 100, 200, 80)]
    expect(screenNamesOf({ reading: [], boxes, textPixels: LEGIBLE_PIXELS, toWindow: identity, window: WINDOW }))
      .toEqual([])
    expect(screenNamesOf({ reading: [], boxes, textPixels: null, toWindow: identity, window: WINDOW })).toEqual([])
  })

  it('names the boxes in the window on each, largest first, leaving out a name that would cover another', () => {
    const boxes = [
      mark('small', 400, 300, 40, 20),
      mark('large', 300, 250, 300, 120),
      mark('apart', 100, 450, 120, 60),
      mark('outside', 2000, 300, 200, 80),
    ]
    const names = screenNamesOf({ reading: [], boxes, textPixels: 3, toWindow: identity, window: WINDOW })
    expect(names.map((name) => name.id)).toEqual(['large', 'apart'])
    expect(names.every((name) => name.place === 'on')).toBe(true)
    expect(names[0].at).toEqual({ x: 450, y: 310 })
  })

  it('names a reading\'s elements alone while there is one, the selection first and above each', () => {
    const reading = [mark('reached', 300, 200, 100, 50), mark('chosen', 310, 205, 100, 50, true)]
    const boxes = [mark('other', 600, 400, 200, 80)]
    const names = screenNamesOf({ reading, boxes, textPixels: 3, toWindow: identity, window: WINDOW })
    // The two overlap: the selection keeps the room.
    expect(names.map((name) => name.id)).toEqual(['chosen'])
    expect(names[0]).toMatchObject({ place: 'above', selected: true, at: { x: 360, y: 205 } })
  })

  it('places names in the window by the window\'s own reading of the picture', () => {
    const boxes = [mark('far', 5000, 1000, 400, 200)]
    const toWindow = ({ x, y }: { x: number; y: number }) => ({ x: x / 10, y: y / 10 })
    expect(screenNamesOf({ reading: [], boxes, textPixels: 1, toWindow, window: WINDOW })[0].at)
      .toEqual({ x: 520, y: 110 })
  })
})

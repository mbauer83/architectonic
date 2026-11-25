// What a diagram window opens on (Q19): the whole picture where it reads, its width where it nearly does,
// and 60 % on its top-left corner where the whole would be below 35 %.
import { describe, expect, it } from 'vitest'
import { LARGE_BELOW, LARGE_OPENING, openingFramingOf, wholeFramingOf, wholeScaleOf } from './viewportFraming'

const picture = (width: number, height: number, left = 0, top = 0) =>
  ({ left, top, right: left + width, bottom: top + height })
const WINDOW = { width: 1100, height: 700 }

describe('the framing a diagram window opens on', () => {
  it('shows the whole of a picture that fits at half its size or more, centred across the window', () => {
    const framing = openingFramingOf(picture(1000, 600), WINDOW)!
    expect(framing.scale).toBeCloseTo(wholeScaleOf(picture(1000, 600), WINDOW))
    expect(framing.scale).toBeGreaterThanOrEqual(0.5)
    expect(framing.tx).toBeCloseTo((1100 - 1000 * framing.scale) / 2)
  })

  it('fits a picture that would shrink below half but not below 35 % to the window\'s width', () => {
    const wide = picture(2600, 600)
    expect(wholeScaleOf(wide, WINDOW)).toBeGreaterThanOrEqual(LARGE_BELOW)
    expect(wholeScaleOf(wide, WINDOW)).toBeLessThan(0.5)
    expect(openingFramingOf(wide, WINDOW)!.scale).toBeCloseTo((1100 - 48) / 2600)
  })

  it('opens a picture that would fit only below 35 % at 60 % on its top-left corner', () => {
    // The Application Cooperation view: 34 237 × 1 944, about 3 % fitted.
    const large = picture(34237, 1944, 7, 3)
    expect(wholeScaleOf(large, WINDOW)).toBeLessThan(LARGE_BELOW)
    const framing = openingFramingOf(large, WINDOW)!
    expect(framing.scale).toBe(LARGE_OPENING)
    // The picture's top-left corner sits just inside the window's top-left corner.
    expect(framing.tx + 7 * LARGE_OPENING).toBeCloseTo(24)
    expect(framing.ty + 3 * LARGE_OPENING).toBeGreaterThan(0)
    expect(framing.ty + 3 * LARGE_OPENING).toBeLessThan(50)
  })

  it('centres a large picture narrower than the window at 60 % across it', () => {
    const tall = picture(800, 20000)
    const framing = openingFramingOf(tall, WINDOW)!
    expect(framing.scale).toBe(LARGE_OPENING)
    expect(framing.tx).toBeCloseTo((1100 - 800 * LARGE_OPENING) / 2)
  })

  it('opens nothing for a picture with no extent', () => {
    expect(openingFramingOf(picture(0, 0), WINDOW)).toBeNull()
  })
})

describe('fitting the whole diagram', () => {
  it('is the opening framing where the window opens on the whole picture', () => {
    expect(wholeFramingOf(picture(1000, 600), WINDOW)).toEqual(openingFramingOf(picture(1000, 600), WINDOW))
  })

  it('shows all of a large picture, centred both ways, so a zoom about the centre zooms into it', () => {
    const large = picture(34237, 1944)
    const framing = wholeFramingOf(large, WINDOW)!
    expect(framing.scale).toBeCloseTo(wholeScaleOf(large, WINDOW))
    const top = framing.ty
    const bottom = framing.ty + 1944 * framing.scale
    expect((top + bottom) / 2).toBeGreaterThan(300)
    expect((top + bottom) / 2).toBeLessThan(400)
    expect(framing.tx + 34237 * framing.scale).toBeLessThanOrEqual(1100)
  })
})

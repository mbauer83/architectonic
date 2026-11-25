/**
 * The canvas's one paint order: shapes by nesting, a container before its contents, then lines, then
 * labels. The shape last moved is brought forward, a widened box never covers a sibling it overlaps,
 * and a line goes under whatever hides one of its ends.
 */
import { describe, expect, it } from 'vitest'
import type { Extent } from '../../../domain/layout/geometry'
import { overlaps } from '../../../domain/layout/geometry'
import { LINE_DRAWING, SHAPE_DRAWING } from '../../../domain/layout/lab/__tests__/labDrawingFixtures'
import type { LayoutGeometry } from '../../../domain/schemas/diagramLayoutGeometry'
import type { Placement } from '../../../domain/layout/lab/labRouting'
import type { Lift, Painted } from './labPaintOrder'
import { paintOrder, shapeOrder } from './labPaintOrder'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })

const box = (alias: string, inside: string | undefined, extent: Extent) => ({
  alias, kind: 'domain' as const, section: 'boxes' as const, key: undefined, label: alias,
  extent, inside, words: [], title_band: undefined, drawing: SHAPE_DRAWING,
})
const element = (alias: string, inside: string | undefined, extent: Extent) => ({
  alias, key: undefined, label: alias, extent, inside, words: [], outside_label: undefined, drawing: SHAPE_DRAWING,
})
const relation = (index: number, source: string, target: string) => ({
  index, key: `r${index}`, source, target, decorated: [false, true] as [boolean, boolean],
  course: [], label: '', label_size: undefined, drawing: LINE_DRAWING,
})

/**
 * One (holding Inner, holding a) and Two (holding b) side by side, c and d loose below them; a line
 * from b to c, from c to d, and from the box Two to d.
 */
const geometry: LayoutGeometry = {
  artifact_id: 'ARC@1.a.test', name: 'Test', canvas: at(0, 0, 600, 400), backdrop: [],
  surround: [],
  boxes: [
    box('One', undefined, at(0, 0, 200, 150)),
    box('Two', undefined, at(250, 0, 450, 150)),
    box('Inner', 'One', at(10, 30, 190, 140)),
  ],
  elements: [
    element('a', 'Inner', at(20, 60, 120, 100)),
    element('b', 'Two', at(270, 40, 370, 80)),
    element('c', undefined, at(20, 250, 120, 290)),
    element('d', undefined, at(300, 250, 400, 290)),
  ],
  relations: [relation(0, 'b', 'c'), relation(1, 'c', 'd'), relation(2, 'Two', 'd')],
}

const drawn: Placement = {
  boxes: new Map(geometry.boxes.map((shape) => [shape.alias, shape.extent])),
  elements: new Map(geometry.elements.map((shape) => [shape.alias, shape.extent])),
}

/** *placement* with the shapes in *changed* put where it says. */
const placedWith = (changed: Readonly<Record<string, Extent>>, placement: Placement = drawn): Placement => ({
  boxes: new Map([...placement.boxes].map(([alias, extent]) => [alias, changed[alias] ?? extent])),
  elements: new Map([...placement.elements].map(([alias, extent]) => [alias, changed[alias] ?? extent])),
})

const shapesOf = (placement: Placement, lift: Lift | null): string[] =>
  shapeOrder(geometry, placement, lift).map((shape) => shape.alias)

const named = (piece: Painted): string =>
  piece.kind === 'shape' ? piece.alias : `${piece.kind}:${piece.relation}`

const placeOf = (order: readonly Painted[], name: string): number => order.map(named).indexOf(name)

describe('the canvas paint order', () => {
  it('paints a box, then everything in it, siblings as drawn; then every line, then every label', () => {
    expect(paintOrder(geometry, drawn, null).map(named)).toEqual([
      'One', 'Inner', 'a', 'Two', 'b', 'c', 'd',
      'line:0', 'line:1', 'line:2', 'label:0', 'label:1', 'label:2',
    ])
  })

  it('brings the unit holding the shape last moved in front of its siblings', () => {
    expect(shapesOf(drawn, { alias: 'a', how: 'moved' })).toEqual(['Two', 'b', 'c', 'd', 'One', 'Inner', 'a'])
  })

  it('paints every box before what it holds, whatever was lifted and however', () => {
    const inside = new Map([...geometry.boxes, ...geometry.elements].map((shape) => [shape.alias, shape.inside]))
    const everyLift = [...inside.keys()].flatMap((alias): Lift[] =>
      [{ alias, how: 'moved' }, { alias, how: 'resized' }])
    for (const lift of everyLift) {
      const order = shapesOf(placedWith({ One: at(0, 0, 400, 300) }), lift)
      for (const [alias, holder] of inside) {
        if (holder !== undefined && holder !== null) expect(order.indexOf(holder), `${holder} before ${alias}`).toBeLessThan(order.indexOf(alias))
      }
    }
  })

  it('paints a widened box under the siblings it now overlaps, and over the ones it does not', () => {
    const widened = placedWith({ One: at(0, 0, 200, 270) })
    expect(overlaps(at(0, 0, 200, 270), at(20, 250, 120, 290))).toBe(true)

    const order = shapesOf(widened, { alias: 'One', how: 'resized' })
    expect(order.indexOf('One')).toBeLessThan(order.indexOf('c'))
    expect(order.indexOf('Two')).toBeLessThan(order.indexOf('One'))
    expect(order.indexOf('d')).toBeLessThan(order.indexOf('One'))
  })

  it('paints a widened inner box under the siblings it overlaps, inside its own box', () => {
    const geometryWithSibling: LayoutGeometry = {
      ...geometry,
      elements: [...geometry.elements, element('e', 'One', at(150, 100, 190, 140))],
    }
    const placement = placedWith({ Inner: at(10, 30, 195, 145), e: at(150, 100, 190, 140) }, {
      boxes: drawn.boxes,
      elements: new Map([...drawn.elements, ['e', at(150, 100, 190, 140)]]),
    })
    const order = shapeOrder(geometryWithSibling, placement, { alias: 'Inner', how: 'resized' }).map((one) => one.alias)
    expect(order.indexOf('Inner')).toBeLessThan(order.indexOf('e'))
    expect(order.indexOf('One')).toBeLessThan(order.indexOf('Inner'))
  })

  it('paints a box moved over an element over it, and the element\'s lines under the box', () => {
    // Two dragged down over c: Two hides c, so the lines into c go under Two with it.
    const placement = placedWith({ Two: at(0, 200, 200, 350), b: at(20, 240, 120, 280) })
    const order = paintOrder(geometry, placement, { alias: 'Two', how: 'moved' })

    expect(placeOf(order, 'c')).toBeLessThan(placeOf(order, 'Two'))
    for (const line of ['line:1', 'line:0']) {
      expect(placeOf(order, line), line).toBeGreaterThan(placeOf(order, 'c'))
      expect(placeOf(order, line), line).toBeLessThan(placeOf(order, 'Two'))
    }
    expect(placeOf(order, 'label:1')).toBe(placeOf(order, 'line:1') + 1)
    expect(placeOf(order, 'line:2')).toBeGreaterThan(placeOf(order, 'b'))
  })

  it('keeps on top a line whose ends nothing hides, whatever it crosses', () => {
    const order = paintOrder(geometry, drawn, { alias: 'One', how: 'moved' })
    const lastShape = Math.max(...['One', 'Inner', 'a', 'Two', 'b', 'c', 'd'].map((alias) => placeOf(order, alias)))
    expect(placeOf(order, 'line:0')).toBeGreaterThan(lastShape)
  })

  it('sinks a line under a box two levels above its other end, over its far end two levels deep', () => {
    // As Strategy (holding Course of Actions, holding Dogfood) dragged up over Motivation (holding
    // Outcomes, holding the outcome Dogfood's line ends at).
    const nested: LayoutGeometry = {
      ...geometry,
      boxes: [...geometry.boxes, box('Middle', 'Two', at(260, 20, 440, 140))],
      elements: geometry.elements.map((one) => (one.alias === 'b' ? { ...one, inside: 'Middle' } : one)),
      relations: [relation(0, 'b', 'a')],
    }
    const placement: Placement = {
      boxes: new Map([...drawn.boxes, ['Middle', at(260, 20, 440, 140)], ['Two', at(0, 50, 450, 200)]]),
      elements: drawn.elements,
    }
    for (const lift of [{ alias: 'Two', how: 'moved' }, { alias: 'b', how: 'moved' }, { alias: 'b', how: 'resized' }] as const) {
      const order = paintOrder(nested, placement, lift)
      expect(placeOf(order, 'a'), `${lift.alias} ${lift.how}`).toBeLessThan(placeOf(order, 'Two'))
      expect(placeOf(order, 'line:0'), `${lift.alias} ${lift.how}`).toBeGreaterThan(placeOf(order, 'a'))
      expect(placeOf(order, 'line:0'), `${lift.alias} ${lift.how}`).toBeLessThan(placeOf(order, 'Two'))
    }
  })

  it('sinks a line under its own other end where that end is dragged over its far end', () => {
    // c dragged onto d: d is out of sight under c, and so is the line between them.
    const order = paintOrder(geometry, placedWith({ c: at(310, 255, 410, 295) }), { alias: 'c', how: 'moved' })
    expect(placeOf(order, 'line:1')).toBeGreaterThan(placeOf(order, 'd'))
    expect(placeOf(order, 'line:1')).toBeLessThan(placeOf(order, 'c'))
  })

  it('keeps the boxes holding a resized shape in front of the siblings they were in front of', () => {
    // Two was dragged over One; resizing b, which Two holds, leaves Two in front.
    const placement = placedWith({ Two: at(100, 0, 300, 150), b: at(120, 40, 230, 80) })
    const order = shapesOf(placement, { alias: 'b', how: 'resized' })
    expect(order.indexOf('Two')).toBeGreaterThan(order.indexOf('a'))
  })

  it('does not sink a line into a box under the shapes that box holds', () => {
    const order = paintOrder(geometry, drawn, { alias: 'b', how: 'moved' })
    const lastShape = Math.max(...['One', 'Inner', 'a', 'Two', 'b', 'c', 'd'].map((alias) => placeOf(order, alias)))
    expect(placeOf(order, 'line:2')).toBeGreaterThan(lastShape)
  })
})

describe('the stated stacking', () => {
  it('orders siblings, a box and everything in it painted as one unit', () => {
    const order = shapeOrder(geometry, drawn, null, new Map([['One', 9], ['c', -1]]))
    expect(order.map((one) => one.alias)).toEqual(['c', 'Two', 'b', 'd', 'One', 'Inner', 'a'])
  })
})

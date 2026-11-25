/**
 * The box something new is added to: the innermost box under the point, and what it admits — a
 * computed box by its rule, a stated grouping by the rule it states or anything, a container element
 * the parts the ontology lets it hold.
 */
import { describe, expect, it } from 'vitest'
import type { Extent } from '../geometry'
import type { GeometryBox, LayoutGeometry } from '../../schemas/diagramLayoutGeometry'
import { admitsType, receivingBoxAt } from '../receivingBox'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })
const box = (alias: string, kind: GeometryBox['kind'], extent: Extent, extra: Partial<GeometryBox> = {}): GeometryBox => ({
  alias, kind, section: kind === 'element' ? 'elements' : 'boxes', label: alias, extent, words: [],
  drawing: { tag: 'g', attributes: {}, children: [] }, ...extra,
})

/** Business (computed) holding a type box and a container element; a stated grouping beside them. */
const boxes = [
  box('DOM_business', 'domain', at(0, 0, 400, 300), { key: 'rule-key-1', rule: { domain: 'business' } }),
  box('GRPT_1', 'type', at(10, 30, 150, 150), { inside: 'DOM_business', rule: { type: 'business-actor' } }),
  box('Store', 'element', at(200, 30, 390, 200), { inside: 'DOM_business', key: 'BOB@1.a.store' }),
  box('GRPA_1', 'authored-grouping', at(500, 0, 700, 200), { key: 'grp-front' }),
  box('GRPA_2', 'authored-grouping', at(720, 0, 900, 200), { key: 'grp-apps' }),
]
const geometry: LayoutGeometry = {
  artifact_id: 'ARC@1.a.test', name: 'Test', canvas: at(0, 0, 900, 300), backdrop: [],
  surround: { drawn: at(0, 0, 0, 0), parts: [] }, elements: [], boxes, relations: [],
}
const placed = new Map(boxes.map((one) => [one.alias, one.extent]))
const stated = [
  { id: 'grp-front', label: 'Front', 'entity-ids': ['BAC@1.a.b'] },
  { id: 'grp-outer', label: 'Outer', 'entity-ids': [], groups: [{ id: 'grp-apps', label: 'Apps', 'entity-ids': [], rule: { domain: 'application' } }] },
]
const elementOf = (key: string) => (key === 'BOB@1.a.store' ? { name: 'Order Store', type: 'business-object' } : undefined)
const into = (x: number, y: number) => receivingBoxAt(geometry, placed, { x, y }, stated, elementOf)

describe('the box under a point', () => {
  it('is the innermost one, admitting by the rule the renderer computed it by', () => {
    expect(into(20, 10)).toEqual({ alias: 'DOM_business', label: 'DOM_business', admits: { kind: 'domain', domain: 'business' } })
    expect(into(20, 40)?.admits).toEqual({ kind: 'type', type: 'business-actor' })
  })

  it('is a container element admitting its parts, a listed grouping anything, a ruled one by its rule', () => {
    expect(into(300, 100)).toEqual({
      alias: 'Store', label: 'Order Store', admits: { kind: 'parts', container: 'Store', containerType: 'business-object' },
    })
    expect(into(600, 100)?.admits).toEqual({ kind: 'anything' })
    expect(into(800, 100)?.admits).toEqual({ kind: 'domain', domain: 'application' })
  })

  it('is none on open paper', () => {
    expect(into(450, 280)).toBeNull()
  })
})

describe('what a box admits', () => {
  it('takes a layer, a type, or a container\'s parts once the ontology has said which', () => {
    expect(admitsType({ kind: 'domain', domain: 'business' }, 'business-actor', 'business')).toBe(true)
    expect(admitsType({ kind: 'domain', domain: 'business' }, 'function', 'common')).toBe(false)
    expect(admitsType({ kind: 'type', type: 'role' }, 'service', 'common')).toBe(false)
    const parts = { kind: 'parts', container: 'Store', containerType: 'business-object' } as const
    expect(admitsType(parts, 'business-object', 'business', new Set(['business-object']))).toBe(true)
    expect(admitsType(parts, 'role', 'common', new Set(['business-object']))).toBe(false)
    expect(admitsType({ kind: 'anything' }, 'role', 'common')).toBe(true)
  })
})

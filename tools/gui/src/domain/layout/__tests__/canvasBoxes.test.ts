/**
 * A diagram's boxes edited on its canvas (D9): the computed layer and type boxes written down as ruled
 * groupings the first time one is edited, a box found by its id or by the labels round it, renamed,
 * deleted without what it holds, a type box added, and every ruled box given back to the renderer.
 */
import { describe, expect, it } from 'vitest'
import type { AuthoredGrouping } from '../../authoredGrouping'
import type { LayoutGeometry } from '../../schemas/diagramLayoutGeometry'
import {
  boxChanges, harvestedBoxes, ownedBoxes, renamedBox, statesRuledBoxes, trailOf, withNewBox, withTypeBox, withoutBox,
  withoutRuledBoxes,
} from '../canvasBoxes'

type Box = LayoutGeometry['boxes'][number]
const box = (alias: string, label: string, over: Partial<Box> = {}): Box => ({
  alias, label, kind: 'domain', section: 'boxes', extent: { left: 0, top: 0, right: 1, bottom: 1 }, words: [],
  drawing: { tag: 'g', attributes: {}, children: [] }, ...over,
})
const picture = (boxes: Box[]): LayoutGeometry => ({
  artifact_id: 'ARC@1.a', name: 'A', canvas: { left: 0, top: 0, right: 9, bottom: 9 }, backdrop: [],
  surround: { drawn: { left: 0, top: 0, right: 0, bottom: 0 }, parts: [] }, elements: [], boxes, relations: [],
})

/** Business with two type boxes for one type (once per flow) and one for another; Application; a listed box. */
const COMPUTED = picture([
  box('DOM_business', 'Business', { rule: { domain: 'business' } }),
  box('GRPT_a1', 'Business Service', { kind: 'type', inside: 'DOM_business', rule: { type: 'business-service' } }),
  box('GRPT_a2', 'Business Service', { kind: 'type', inside: 'DOM_business', rule: { type: 'business-service' } }),
  box('GRPT_a3', 'Business Role', { kind: 'type', inside: 'DOM_business', rule: { type: 'business-role' } }),
  box('DOM_application', 'Application', { rule: { domain: 'application' } }),
  box('GRPA_1', 'Front office', { kind: 'authored-grouping', key: 'g-Front1' }),
])
const LISTED: AuthoredGrouping[] = [{ id: 'g-Front1', label: 'Front office', 'entity-ids': ['APP@1.a'] }]

describe('the computed boxes written down', () => {
  it('as ruled groupings nested as drawn, a type boxed twice written once', () => {
    expect(harvestedBoxes(COMPUTED)).toEqual([
      { label: 'Business', 'entity-ids': [], rule: { domain: 'business' }, groups: [
        { label: 'Business Service', 'entity-ids': [], rule: { type: 'business-service' } },
        { label: 'Business Role', 'entity-ids': [], rule: { type: 'business-role' } },
      ] },
      { label: 'Application', 'entity-ids': [], rule: { domain: 'application' } },
    ])
  })

  it('only when the diagram states no ruled grouping, after its listed ones', () => {
    const owned = ownedBoxes(LISTED, COMPUTED)
    expect(owned.map((one) => one.label)).toEqual(['Front office', 'Business', 'Application'])
    expect(ownedBoxes(owned, COMPUTED)).toBe(owned)
    expect(statesRuledBoxes(LISTED)).toBe(false)
    expect(statesRuledBoxes(owned)).toBe(true)
  })
})

describe('a box found and edited', () => {
  const owned = ownedBoxes(LISTED, COMPUTED)

  it('is found by its id, else by the labels of the boxes round it', () => {
    expect(trailOf(owned, COMPUTED, 'GRPA_1')).toEqual([0])
    expect(trailOf(owned, COMPUTED, 'GRPT_a3')).toEqual([1, 1])
    expect(trailOf(owned, COMPUTED, 'nowhere')).toBeNull()
  })

  it('is renamed, deleted with its boxes taking its place, and given a type box', () => {
    expect(renamedBox(owned, [1, 1], 'Roles')[1].groups?.[1].label).toBe('Roles')
    expect(withoutBox(owned, [1]).map((one) => one.label))
      .toEqual(['Front office', 'Business Service', 'Business Role', 'Application'])
    expect(withTypeBox(owned, [2], 'application-component', 'Application Component')[2].groups)
      .toEqual([{ label: 'Application Component', 'entity-ids': [], rule: { type: 'application-component' } }])
  })

  it('deleted from inside a listed box, gives the box round it what it listed', () => {
    const nested: AuthoredGrouping[] = [
      { id: 'g-Outer1', label: 'Outer', 'entity-ids': ['A'], groups: [{ id: 'g-Inner1', label: 'Inner', 'entity-ids': ['B'] }] },
    ]
    expect(withoutBox(nested, [0, 0])).toEqual([{ id: 'g-Outer1', label: 'Outer', 'entity-ids': ['A', 'B'], groups: [] }])
  })

  it('puts drawings in a new listed box, out of the listed box they were in, which goes once empty', () => {
    expect(withNewBox(LISTED, ['APP@1.a.slug', 'APP@2.b'], 'Review')).toEqual([
      { label: 'Review', 'entity-ids': ['APP@1.a.slug', 'APP@2.b'] },
    ])
    const kept = withNewBox([...LISTED, { label: 'Other', 'entity-ids': ['APP@3.c'] }], ['APP@1.a'], 'Review')
    expect(kept.map((one) => [one.label, one['entity-ids']])).toEqual([['Other', ['APP@3.c']], ['Review', ['APP@1.a']]])
  })

  it('gives every ruled box back to the renderer, keeping the listed ones', () => {
    expect(withoutRuledBoxes(owned)).toEqual(LISTED)
  })
})

describe('what Save lists for the boxes', () => {
  const owned = ownedBoxes(LISTED, COMPUTED)

  it('names a box deleted, renamed and added, counted against the boxes as drawn', () => {
    const now = withTypeBox(renamedBox(withoutBox(owned, [2]), [1], 'Customer side'), [1], 'business-actor', 'Actor')
    expect(boxChanges(LISTED, now, COMPUTED).map((row) => row.text)).toEqual([
      'Box added: Actor', 'Box renamed: Business → Customer side',
      'Box deleted: Application — what it held stays on the diagram',
    ])
  })

  it('lists nothing when the boxes are as they were, and one row for returning to automatic boxes', () => {
    expect(boxChanges(LISTED, withoutRuledBoxes(owned), COMPUTED)).toEqual([])
    expect(boxChanges(owned, withoutRuledBoxes(owned), COMPUTED).map((row) => row.text))
      .toEqual(['Returned to automatic boxes'])
  })
})

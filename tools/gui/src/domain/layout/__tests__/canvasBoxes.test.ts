/**
 * A diagram's boxes edited on its canvas (D9): the computed layer and type boxes written down as ruled
 * groupings the first time one is edited, a box found by its id or by the labels round it, renamed,
 * deleted without what it holds, a type box added, and every ruled box given back to the renderer.
 */
import { describe, expect, it } from 'vitest'
import type { AuthoredGrouping } from '../../authoredGrouping'
import type { LayoutGeometry } from '../../schemas/diagramLayoutGeometry'
import {
  boxChanges, boxesArranged, boxesDiffer, harvestedBoxes, ownedBoxes, renamedBox, statesRuledBoxes, trailOf,
  withBoxesReturned, withNewBox, withTypeBox, withoutBox, withoutRuledBoxes,
} from '../canvasBoxes'
import { drawnArrangement, moved, resized } from '../canvasArrangement'
import { placementOf } from '../canvasRouting'

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

/** A layer box holding a type box holding one element and an element of its own; an element outside both. */
const at = (left: number, top: number, right: number, bottom: number) => ({ left, top, right, bottom })
const element = (alias: string, extent: ReturnType<typeof at>, inside?: string) => ({
  alias, key: `APP@1.${alias}`, label: alias, extent, inside, words: [], outside_label: undefined,
  drawing: { tag: 'g', attributes: {}, children: [] },
})
const ARRANGED: LayoutGeometry = {
  ...picture([
    box('DOM_business', 'Business', { rule: { domain: 'business' }, extent: at(0, 0, 300, 200) }),
    box('GRPT_role', 'Business Role', {
      kind: 'type', inside: 'DOM_business', rule: { type: 'business-role' }, extent: at(20, 30, 180, 150),
    }),
  ]),
  elements: [
    element('a', at(40, 60, 140, 110), 'GRPT_role'), element('b', at(200, 60, 280, 110), 'DOM_business'),
    element('c', at(400, 60, 500, 110)),
  ],
}

describe('the boxes the session moved or sized, given back', () => {
  const start = drawnArrangement(ARRANGED)

  it('finds a box moved whole, not what it carried, and not an element moved on its own', () => {
    expect(boxesArranged(ARRANGED, start, moved(ARRANGED, start, 'DOM_business', 40, 25))).toEqual(['DOM_business'])
    expect(boxesArranged(ARRANGED, start, moved(ARRANGED, start, 'GRPT_role', 5, 0))).toEqual(['GRPT_role'])
    expect(boxesArranged(ARRANGED, start, moved(ARRANGED, start, 'c', 40, 25))).toEqual([])
  })

  it('puts a moved box back with what it holds, leaving what it does not hold where it was put', () => {
    const now = moved(ARRANGED, moved(ARRANGED, start, 'DOM_business', 40, 25), 'c', 10, 10)
    const back = withBoxesReturned(ARRANGED, start, now)
    expect(back.elements.get('a')).toEqual(at(40, 60, 140, 110))
    expect(back.elements.get('c')).toEqual(at(410, 70, 510, 120))
    expect(boxesArranged(ARRANGED, start, back)).toEqual([])
  })

  it('finds none where a picture drawn again states every box where it stands', () => {
    const fitted = placementOf(ARRANGED, start).boxes
    expect(boxesArranged(ARRANGED, start, { ...start, stated: new Map(fitted) })).toEqual([])
  })

  it('puts a sized box back to the size it was', () => {
    const now = resized(ARRANGED, start, 'DOM_business', at(0, 0, 360, 260))
    expect(boxesArranged(ARRANGED, start, now)).toEqual(['DOM_business'])
    expect(withBoxesReturned(ARRANGED, start, now).stated.size).toBe(0)
  })

  it('differs from the automatic boxes when moved, sized, renamed, created or deleted, and not otherwise', () => {
    const differs = (now: readonly AuthoredGrouping[] | undefined, arrangement = start) =>
      boxesDiffer(LISTED, now, ARRANGED, start, arrangement)
    expect(differs(undefined)).toBe(false)
    expect(differs(LISTED)).toBe(false)
    expect(differs(undefined, moved(ARRANGED, start, 'DOM_business', 40, 25))).toBe(true)
    expect(differs(undefined, resized(ARRANGED, start, 'DOM_business', at(0, 0, 360, 260)))).toBe(true)
    expect(differs(renamedBox(LISTED, [0], 'Back office'))).toBe(true)
    expect(differs(withNewBox(LISTED, ['APP@9.z'], 'Review'))).toBe(true)
    expect(differs([])).toBe(true)
    expect(differs(ownedBoxes(LISTED, COMPUTED))).toBe(true)
  })
})

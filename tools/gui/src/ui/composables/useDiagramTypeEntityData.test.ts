import { describe, expect, it, vi } from 'vitest'
import { useDiagramTypeEntityData } from './useDiagramTypeEntityData'
import type { DiagramContext } from '../../domain'

const GOAL = 'GOL@1.aa.provide-governed-read-access'

/** Only what seeding reads: the saved diagram's own data, its entities and what the body calls them. */
const context = (over: {
  diagram_entities?: unknown, drawn_labels?: Record<string, string>, element_label?: string,
}): DiagramContext => ({
  diagram: { diagram_entities: over.diagram_entities ?? {} },
  entities: [{
    artifact_id: GOAL, name: 'Provide Governed Read Access',
    element_label: over.element_label ?? 'Provide Governed Read Access',
  }],
  drawn_labels: over.drawn_labels ?? {},
} as unknown as DiagramContext)

describe('the diagram’s own data under edit', () => {
  it('starts from the saved data with nothing pending', () => {
    const data = useDiagramTypeEntityData(() => {})
    data.seedFromContext(context({ diagram_entities: { occurrence: [] } }))

    expect(data.typeEntityData.value).toEqual({ occurrence: [] })
  })

  it('carries a hand-laid label into the diagram’s statement as the first pending edit', () => {
    const data = useDiagramTypeEntityData(() => {})
    data.seedFromContext(context({
      diagram_entities: { occurrence: [{ id: 'occ-2', backing_entity_id: GOAL }] },
      drawn_labels: { [GOAL]: 'Read Access', 'occ-2': 'Provide Governed Read Access' },
    }))

    expect(data.typeEntityData.value.display_labels).toEqual({ [GOAL]: 'Read Access' })
  })

  it('states a label for one instance and tells the view something moved', () => {
    const onChange = vi.fn()
    const data = useDiagramTypeEntityData(onChange)
    data.seedFromContext(context({}))

    data.setInstanceLabel('occ-2', 'Again')

    expect(data.typeEntityData.value.display_labels).toEqual({ 'occ-2': 'Again' })
    expect(onChange).toHaveBeenCalledTimes(1)
  })

  it('withdraws a label with null, leaving the saved base untouched', () => {
    const data = useDiagramTypeEntityData(() => {})
    data.seedFromContext(context({ diagram_entities: { display_labels: { [GOAL]: 'Saved' } } }))

    data.setInstanceLabel(GOAL, null)

    // The pending data says the statement is withdrawn — an empty map, not a missing key, because
    // a merge over the saved base could not otherwise take the saved label away.
    expect(data.typeEntityData.value.display_labels).toEqual({})
    data.seedFromContext(context({ diagram_entities: { display_labels: { [GOAL]: 'Saved' } } }))
    expect(data.typeEntityData.value.display_labels).toEqual({ [GOAL]: 'Saved' })
  })
})

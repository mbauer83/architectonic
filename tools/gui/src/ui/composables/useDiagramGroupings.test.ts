import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useDiagramGroupings } from './useDiagramGroupings'
import { addOccurrenceFor } from '../lib/archimateOccurrences'
import type { EntityDisplayInfo } from '../../domain'

const entity = (id: string, name: string): EntityDisplayInfo => ({
  artifact_id: id, name, artifact_type: 'goal', domain: 'motivation', subdomain: '',
  status: 'active', display_alias: name.toUpperCase().replace(/\W/g, '_'),
  element_type: 'goal', element_label: name, diagram_internal: false,
})

const ONE = entity('GOL@1.aa.one', 'One')
const TWO = entity('GOL@1.bb.two', 'Two')

const setup = () => {
  const entities = ref([ONE, TWO])
  const diagramEntities = ref<Record<string, unknown>>({})
  /** What a view does when a box needs its own drawing of an entity already on the picture. */
  const drawAgain = (e: EntityDisplayInfo): string => {
    const { diagramEntities: next, occurrenceId } = addOccurrenceFor(diagramEntities.value, e)
    diagramEntities.value = next
    return occurrenceId
  }
  return { ...useDiagramGroupings(entities, diagramEntities), diagramEntities, drawAgain }
}

describe('putting a drawing in a box', () => {
  it('holds it', () => {
    const { groupings, addMember } = setup()
    groupings.value = [{ label: 'Forces', 'entity-ids': [] }]

    addMember(0, ONE.artifact_id)

    expect(groupings.value[0]['entity-ids']).toEqual([ONE.artifact_id])
  })

  it('does not hold it twice — saying it again says nothing', () => {
    const { groupings, addMember } = setup()
    groupings.value = [{ label: 'Forces', 'entity-ids': [ONE.artifact_id] }]

    addMember(0, ONE.artifact_id)

    expect(groupings.value[0]['entity-ids']).toEqual([ONE.artifact_id])
  })

  it('leaves the other boxes alone', () => {
    const { groupings, addMember } = setup()
    groupings.value = [
      { label: 'A', 'entity-ids': [] }, { label: 'B', 'entity-ids': [TWO.artifact_id] },
    ]

    addMember(0, ONE.artifact_id)

    expect(groupings.value[1]['entity-ids']).toEqual([TWO.artifact_id])
  })
})

describe('which box holds a drawing', () => {
  it('names it, so a boxed drawing does not read as a loose one', () => {
    const { groupings, labelOfDrawing } = setup()
    groupings.value = [{ label: 'Forces', 'entity-ids': [ONE.artifact_id] }]

    expect(labelOfDrawing(ONE.artifact_id)).toBe('Forces')
    expect(labelOfDrawing(TWO.artifact_id)).toBeUndefined()
  })

  it('follows a rename, so a row never shows a box label that no longer exists', () => {
    const { groupings, labelOfDrawing } = setup()
    groupings.value = [{ label: 'Forces', 'entity-ids': [ONE.artifact_id] }]

    groupings.value = [{ label: 'Constraints', 'entity-ids': [ONE.artifact_id] }]

    expect(labelOfDrawing(ONE.artifact_id)).toBe('Constraints')
  })

  it('reaches a drawing inside a nested box', () => {
    const { groupings, labelOfDrawing } = setup()
    groupings.value = [{
      label: 'Outer', 'entity-ids': [], groups: [{ label: 'Inner', 'entity-ids': [ONE.artifact_id] }],
    }]

    expect(labelOfDrawing(ONE.artifact_id)).toBe('Inner')
  })

  it('lists what one box holds, so a new member can be wired to it', () => {
    const { groupings, membersOf } = setup()
    groupings.value = [{ label: 'Forces', 'entity-ids': [ONE.artifact_id, TWO.artifact_id] }]

    expect(membersOf(0)).toEqual([ONE.artifact_id, TWO.artifact_id])
    expect(membersOf(5)).toEqual([])
  })
})

describe('what the picker offers', () => {
  it('offers every drawing, named so a reader can tell them apart', () => {
    const { candidates, drawAgain } = setup()
    drawAgain(ONE)

    expect(candidates.value.map((c) => c.label)).toEqual(['One', 'One (2nd)', 'Two'])
  })
})

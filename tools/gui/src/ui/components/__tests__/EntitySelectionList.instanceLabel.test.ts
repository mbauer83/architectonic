// @vitest-environment jsdom
//
// A row shows the label its instance carries on this diagram, and offers to change it.
//
// Driven through a real mount because the defect this guards is a *missing* affordance: nothing in
// the helpers could say whether the list put the label, or a way to edit it, on screen at all.

import { afterEach, describe, expect, it } from 'vitest'
import { createApp, h, nextTick, type App } from 'vue'
import EntitySelectionList from '../EntitySelectionList.vue'
import type { EntityDisplayInfo } from '../../../domain'

/** The list's row shape, spelled here because a `.vue` module exports no named types to a test. */
type EntityRow = {
  entity: EntityDisplayInfo
  occurrenceId: string | null
  occurrenceOrdinal?: string
  actionKind?: 'remove' | 'mark-remove'
}

const GOAL: EntityDisplayInfo = {
  artifact_id: 'GOL@1.aa.provide-governed-read-access', name: 'Provide Governed Read Access',
  artifact_type: 'goal', domain: 'motivation', subdomain: '', status: 'active', display_alias: 'GOL_aa',
  element_type: 'goal', element_label: 'Provide Governed Read Access', diagram_internal: false,
}

let app: App | null = null
let host: HTMLDivElement

const mounted = (props: {
  rows: EntityRow[], diagramEntities?: Record<string, unknown>, drawnLabels?: Record<string, string>,
  labelsSupported?: boolean,
}) => {
  const emitted: Array<[string, string | null]> = []
  host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp({
    render: () => h(EntitySelectionList, {
      candidateConnections: [], includedEntityIds: [GOAL.artifact_id], includedConnectionIds: [],
      relatedEntitiesById: {}, expandedConnectionEntityIds: [], expandedRelatedEntityIds: [],
      occurrencesSupported: true,
      ...props,
      onSetDisplayLabel: (instanceId: string, label: string | null) => { emitted.push([instanceId, label]) },
    }),
  })
  app.mount(host)
  return { host, emitted }
}

afterEach(() => { app?.unmount(); app = null; host.remove() })

const ROWS: EntityRow[] = [
  { entity: GOAL, occurrenceId: null },
  { entity: GOAL, occurrenceId: 'occ-2', occurrenceOrdinal: '2nd', actionKind: 'remove' },
]

describe('what a row says about its instance’s label', () => {
  it('says nothing beside a name the box carries as it is', () => {
    const { host } = mounted({ rows: ROWS, labelsSupported: true })

    expect(host.querySelectorAll('.entity-label')).toHaveLength(0)
    expect(host.querySelectorAll('.label-btn')).toHaveLength(2)
  })

  it('shows the label this diagram states, on the instance it is stated for', () => {
    const { host } = mounted({
      rows: ROWS, labelsSupported: true,
      diagramEntities: { display_labels: { 'occ-2': 'Again' } },
    })

    const chips = [...host.querySelectorAll('.entity-label')].map((el) => el.textContent?.trim())
    expect(chips).toEqual(['as: Again'])
  })

  it('shows what a hand-laid body calls the instance when the diagram states nothing', () => {
    const { host } = mounted({
      rows: ROWS, labelsSupported: true, drawnLabels: { [GOAL.artifact_id]: 'Read Access' },
    })

    expect(host.querySelector('.entity-label')?.textContent?.trim()).toBe('as: Read Access')
  })

  it('offers no label control on a diagram type whose instances cannot carry one', () => {
    const { host } = mounted({ rows: ROWS, labelsSupported: false, drawnLabels: { [GOAL.artifact_id]: 'X' } })

    expect(host.querySelectorAll('.label-btn')).toHaveLength(0)
    expect(host.querySelectorAll('.entity-label')).toHaveLength(0)
  })
})

describe('changing the label', () => {
  const type = async (input: HTMLInputElement, value: string) => {
    input.value = value
    input.dispatchEvent(new Event('input'))
    await nextTick()
  }

  it('opens prefilled with what the box carries and reports the new label for that instance', async () => {
    const { host, emitted } = mounted({ rows: ROWS, labelsSupported: true })

    host.querySelectorAll<HTMLButtonElement>('.label-btn')[1].click()
    await nextTick()
    const input = host.querySelector<HTMLInputElement>('.dle__input')!
    expect(input.value).toBe('Provide Governed Read Access')

    await type(input, '  Read Access  ')
    host.querySelector<HTMLFormElement>('.dle')!.dispatchEvent(new Event('submit'))
    await nextTick()

    expect(emitted).toEqual([['occ-2', 'Read Access']])
    expect(host.querySelector('.dle')).toBeNull()
  })

  it('reports a withdrawal rather than a label that merely repeats the element’s name', async () => {
    const { host, emitted } = mounted({
      rows: ROWS, labelsSupported: true, diagramEntities: { display_labels: { [GOAL.artifact_id]: 'Short' } },
    })

    host.querySelectorAll<HTMLButtonElement>('.label-btn')[0].click()
    await nextTick()
    await type(host.querySelector<HTMLInputElement>('.dle__input')!, 'Provide Governed Read Access')
    host.querySelector<HTMLFormElement>('.dle')!.dispatchEvent(new Event('submit'))
    await nextTick()

    expect(emitted).toEqual([[GOAL.artifact_id, null]])
  })

  it('offers to use the element’s name only where the diagram states a label', async () => {
    const stated = mounted({
      rows: ROWS, labelsSupported: true, diagramEntities: { display_labels: { [GOAL.artifact_id]: 'Short' } },
    })
    stated.host.querySelectorAll<HTMLButtonElement>('.label-btn')[0].click()
    await nextTick()
    expect(stated.host.querySelector('.dle__reset')).not.toBeNull()
    stated.host.querySelector<HTMLButtonElement>('.dle__reset')!.click()
    await nextTick()
    expect(stated.emitted).toEqual([[GOAL.artifact_id, null]])
    app?.unmount(); host.remove()

    const unstated = mounted({ rows: ROWS, labelsSupported: true })
    unstated.host.querySelectorAll<HTMLButtonElement>('.label-btn')[0].click()
    await nextTick()
    expect(unstated.host.querySelector('.dle__reset')).toBeNull()
  })
})

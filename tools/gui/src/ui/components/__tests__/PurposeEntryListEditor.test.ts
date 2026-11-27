// @vitest-environment jsdom
//
// A purpose list's element picker offers only the types the ontology admits for that list — the
// server's write-help declaration — and none at all for a list that admits no reference.

import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick, type App } from 'vue'
import { Effect } from 'effect'
import PurposeEntryListEditor from '../PurposeEntryListEditor.vue'
import { modelServiceKey } from '../../keys'
import type { EntityDisplayInfo } from '../../../domain'
import type { PurposeList } from '../../../domain/purposeLines'
import type { ModelService } from '../../../application/ModelService'

const entity = (artifact_id: string, artifact_type: string): EntityDisplayInfo => ({
  artifact_id, name: artifact_id, artifact_type, domain: 'motivation', subdomain: '', status: 'active',
  display_alias: artifact_id, element_type: artifact_type, element_label: artifact_id, diagram_internal: false,
})
const STAKEHOLDER = entity('STK@1.aa.ops', 'stakeholder')
const COMPONENT = entity('APP@1.bb.shop', 'application-component')

let app: App | null = null
let host: HTMLDivElement

const settle = async () => {
  for (let tick = 0; tick < 4; tick += 1) {
    await Promise.resolve()
    await nextTick()
  }
}

const mounted = async (list: PurposeList, admitted: { stakeholders: string[], concerns: string[] }) => {
  host = document.createElement('div')
  document.body.appendChild(host)
  const searchEntityDisplay = vi.fn(() => Effect.succeed({ items: [STAKEHOLDER, COMPONENT], next_cursor: null }))
  const svc = {
    getWriteHelp: vi.fn(() => Effect.succeed({
      entity_types_by_domain: { motivation: ['stakeholder', 'goal'] },
      entity_type_catalog: {},
      purpose_line_entity_types: admitted,
    })),
    searchEntityDisplay,
  } as unknown as ModelService
  const props = { modelValue: [], list, label: 'For', proseHint: 'in words' }
  app = createApp({ render: () => h(PurposeEntryListEditor, props) })
  app.provide(modelServiceKey, svc)
  app.mount(host)
  await settle()
  return { searchEntityDisplay }
}

const pickerInput = () => host.querySelector<HTMLInputElement>('input[type="search"]')

afterEach(() => { app?.unmount(); app = null; host.remove() })

describe('the element picker of a purpose list', () => {
  it('searches only the types admitted for its list, and drops any other hit', async () => {
    const { searchEntityDisplay } = await mounted('stakeholders', { stakeholders: ['stakeholder'], concerns: ['goal'] })

    pickerInput()!.dispatchEvent(new Event('focus'))
    await settle()

    expect(searchEntityDisplay).toHaveBeenCalledWith(expect.objectContaining({ entityTypes: ['stakeholder'] }))
    const offered = [...host.querySelectorAll('[data-result]')].map((row) => row.textContent ?? '')
    expect(offered.some((text) => text.includes(STAKEHOLDER.name))).toBe(true)
    expect(offered.some((text) => text.includes(COMPONENT.name))).toBe(false)
  })

  it('narrows the concerns list by its own declaration', async () => {
    const { searchEntityDisplay } = await mounted('concerns', { stakeholders: ['stakeholder'], concerns: ['goal'] })

    pickerInput()!.dispatchEvent(new Event('focus'))
    await settle()

    expect(searchEntityDisplay).toHaveBeenCalledWith(expect.objectContaining({ entityTypes: ['goal'] }))
  })

  it('offers no picker where the list admits no reference, leaving prose', async () => {
    await mounted('stakeholders', { stakeholders: [], concerns: ['goal'] })

    expect(pickerInput()).toBeNull()
    expect(host.querySelector('.prose-input')).not.toBeNull()
  })
})

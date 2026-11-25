// @vitest-environment jsdom
//
// *Save as diagram* (S3): the view a candidate is drawn on, saved as a diagram over the candidate's current
// version, named as the author chose; the page is told which diagram it was, and a refusal is said in words.

import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick, type App } from 'vue'
import { Effect } from 'effect'
import SaveAsDiagram from '../candidates/SaveAsDiagram.vue'
import { modelServiceKey } from '../../keys'
import type { ModelService } from '../../../application/ModelService'

const ID = 'CAND@1.abc.searched'

let app: App | null = null
let host: HTMLDivElement

const settle = async () => {
  await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  await nextTick()
}

const mounted = async (save: ModelService['saveCandidateDiagram']) => {
  const saved = vi.fn()
  const readCandidate = vi.fn(() => Effect.succeed({ record: { id: ID }, version: 'v7' }))
  const saveCandidateDiagram = vi.fn(save)
  host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp({
    render: () => h(SaveAsDiagram, { candidateId: ID, name: 'Searched', reason: 'sketch', onSaved: saved }),
  })
  app.provide(modelServiceKey, { readCandidate, saveCandidateDiagram } as Partial<ModelService> as ModelService)
  app.mount(host)
  await settle()
  return { saved, saveCandidateDiagram }
}

afterEach(() => { app?.unmount(); app = null; host.remove() })

describe('Save as diagram', () => {
  it('says the diagram is written and the candidate is not, and saves over the current version', async () => {
    const { saved, saveCandidateDiagram } = await mounted(() => Effect.succeed({
      candidate: ID, dry_run: false, diagram: 'ARC@2.def.promotion', name: 'Promotion', entities: 3, relations: 2,
      version: 'v8',
    }))
    expect(host.textContent).toContain('Nothing this candidate changes is written before it is applied')
    const name = host.querySelector<HTMLInputElement>('[data-testid="save-as-diagram-name"]')!
    expect(name.value).toBe('Searched')
    name.value = 'Promotion'
    name.dispatchEvent(new Event('input'))

    host.querySelector<HTMLButtonElement>('[data-testid="save-as-diagram-confirm"]')!.click()
    await settle()

    expect(saveCandidateDiagram).toHaveBeenCalledWith(ID, 'v7', 'Promotion')
    expect(saved).toHaveBeenCalledWith('ARC@2.def.promotion')
  })

  it('says why a save was refused, and tells the page nothing', async () => {
    const { saved } = await mounted(() => Effect.fail({
      _tag: 'HttpError', status: 422, message: 'reads over nothing the model holds, so there is no view to save',
    } as never))

    host.querySelector<HTMLButtonElement>('[data-testid="save-as-diagram-confirm"]')!.click()
    await settle()

    expect(host.querySelector('[role="alert"]')?.textContent).toContain('no view to save')
    expect(saved).not.toHaveBeenCalled()
  })
})

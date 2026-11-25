// @vitest-environment jsdom
//
// *Save as diagram* on a viewpoint's picture (A-04.11): the elements the execution found and the model's
// relations among them, written through the one diagram create as the layered type the picture is drawn
// as; a derived relation is the viewpoint's reading and is not written. A refusal is said in words.

import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick, type App } from 'vue'
import { Effect } from 'effect'
import ViewpointSaveAsDiagram from '../ViewpointSaveAsDiagram.vue'
import { modelServiceKey } from '../../keys'
import type { ModelService } from '../../../application/ModelService'
import type { ViewpointExecutionResult } from '../../../domain/schemas/viewpoints'

let app: App | null = null
let host: HTMLDivElement
afterEach(() => { app?.unmount(); app = null; host.remove() })

const settle = async () => {
  await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  await nextTick()
}

const execution = {
  entities: [{ id: 'APP@1.a.indexer', name: 'Indexer' }, { id: 'APP@2.b.store', name: 'Store' }],
  connections: [
    { id: 'APP@1.a---APP@2.b@@archimate-serving', certainty: null },
    { id: 'derived:APP@1.a---APP@2.b@@archimate-flow', certainty: 'certain' },
  ],
} as unknown as ViewpointExecutionResult

const mounted = async (createDiagram: ModelService['createDiagram']) => {
  const saved = vi.fn()
  const create = vi.fn(createDiagram)
  host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp({ render: () => h(ViewpointSaveAsDiagram, { name: 'Application Cooperation', execution, onSaved: saved }) })
  app.provide(modelServiceKey, { createDiagram: create } as Partial<ModelService> as ModelService)
  app.mount(host)
  await settle()
  host.querySelector<HTMLButtonElement>('[data-testid="save-as-diagram-confirm"]')!.click()
  await settle()
  return { saved, create }
}

describe('saving a viewpoint\'s picture as a diagram', () => {
  it('writes its elements and the model\'s relations among them, and says which diagram it wrote', async () => {
    const { saved, create } = await mounted(() => Effect.succeed({
      wrote: true, artifact_id: 'ARC@3.c.application-cooperation',
    } as never))
    expect(create).toHaveBeenCalledWith({
      diagram_type: 'archimate-layered', name: 'Application Cooperation',
      entity_ids: ['APP@1.a.indexer', 'APP@2.b.store'],
      connection_ids: ['APP@1.a---APP@2.b@@archimate-serving'],
      dry_run: false,
    })
    expect(saved).toHaveBeenCalledWith('ARC@3.c.application-cooperation')
    expect(host.textContent).toContain('2 elements')
  })

  it('says why the write was refused, and tells the page nothing', async () => {
    const { saved } = await mounted(() => Effect.succeed({
      wrote: false, artifact_id: '', verification: { valid: false, issues: [{ code: 'E101', message: 'refused' }] },
    } as never))
    expect(host.querySelector('[role="alert"]')?.textContent).toContain('E101: refused')
    expect(saved).not.toHaveBeenCalled()
  })
})

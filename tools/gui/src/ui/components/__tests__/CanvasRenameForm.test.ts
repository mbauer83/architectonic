// @vitest-environment jsdom
//
// Renaming an element on the canvas says how far the rename reaches, in words that agree with the count:
// one other diagram, several, or none.

import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick, type App } from 'vue'
import { Effect } from 'effect'
import CanvasRenameForm from '../CanvasRenameForm.vue'
import { modelServiceKey } from '../../keys'
import type { ModelService } from '../../../application/ModelService'

const ID = 'APP@1.abc.indexer'
const HERE = 'ARC@1.here'

let app: App | null = null
let host: HTMLDivElement

const reach = async (diagrams: readonly string[]): Promise<string> => {
  const getEntity = vi.fn(() => Effect.succeed({
    referenced_in_diagrams: [HERE, ...diagrams].map((artifact_id) => ({ artifact_id })),
  }))
  host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp({
    render: () => h(CanvasRenameForm, { element: { id: ID, name: 'Indexer' }, diagramId: HERE, drafted: false }),
  })
  app.provide(modelServiceKey, { getEntity } as unknown as ModelService)
  app.mount(host)
  await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  await nextTick()
  return host.querySelector('.cp-note')?.textContent?.trim() ?? ''
}

afterEach(() => { app?.unmount(); app = null; host.remove() })

describe('how far a rename on the canvas reaches', () => {
  it('names one other diagram in the singular', async () => {
    expect(await reach(['ARC@2.there'])).toBe('Also renamed on 1 other diagram')
  })

  it('names several in the plural', async () => {
    expect(await reach(['ARC@2.there', 'ARC@3.yonder'])).toBe('Also renamed on 2 other diagrams')
  })

  it('says when no other diagram draws it', async () => {
    expect(await reach([])).toBe('No other diagram draws it')
  })
})

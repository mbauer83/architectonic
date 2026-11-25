// @vitest-environment jsdom
//
// Deleting an element from the canvas names the relations that go with it (sketch 03·6, Q16): those
// from it are deleted with it, and one into it from another element keeps Save from deleting it.

import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick, type App } from 'vue'
import { Effect } from 'effect'
import CanvasDeleteConfirm from '../CanvasDeleteConfirm.vue'
import { modelServiceKey } from '../../keys'
import type { ModelService } from '../../../application/ModelService'
import type { ConnectionRecord } from '../../../domain/schemas/connections'
import { DIAGRAM_WORDS } from '../canvasWords'

const ID = 'BOB@1.abc.proposed-change'
const link = (source: string, sourceName: string, type: string, target: string, targetName: string): ConnectionRecord => ({
  artifact_id: `${source}---${target}@@${type}`, source, target, source_name: sourceName, target_name: targetName,
  conn_type: type, version: '1', status: 'active', path: '', content_text: '', specializations: [], metadata: {},
  associated_entities: [],
})

let app: App | null = null
let host: HTMLDivElement

const mounted = async (connections: readonly ConnectionRecord[]) => {
  const getConnections = vi.fn(() => Effect.succeed(connections))
  host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp({ render: () => h(CanvasDeleteConfirm, { name: 'Proposed Change', entityId: ID, words: DIAGRAM_WORDS }) })
  app.provide(modelServiceKey, { getConnections } as Partial<ModelService> as ModelService)
  app.mount(host)
  await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  await nextTick()
  return { getConnections }
}

afterEach(() => { app?.unmount(); app = null; host.remove() })

describe('the delete confirmation on the canvas', () => {
  it('lists the relations that go with the element, and those into it that would stop Save', async () => {
    const { getConnections } = await mounted([
      link(ID, 'Proposed Change', 'archimate-association', 'APP@1.x.repo', 'Repository'),
      link('PRC@1.y.review', 'Review', 'archimate-access', ID, 'Proposed Change'),
    ])
    expect(getConnections).toHaveBeenCalledWith(ID, 'any')
    const going = host.querySelector('[data-testid="delete-relations-going"]')
    expect(going?.textContent).toContain('Its relations go with it')
    expect(going?.nextElementSibling?.textContent).toContain('Proposed Change association Repository')
    const holding = host.querySelector('[data-testid="delete-relations-holding"]')
    expect(holding?.nextElementSibling?.textContent).toContain('Review access Proposed Change')
  })

  it('says when the element has no relations of its own, and names none that hold it', async () => {
    await mounted([])
    expect(host.querySelector('[data-testid="delete-relations-going"]')?.textContent)
      .toContain('no relations of its own')
    expect(host.querySelector('[data-testid="delete-relations-holding"]')).toBeNull()
  })
})

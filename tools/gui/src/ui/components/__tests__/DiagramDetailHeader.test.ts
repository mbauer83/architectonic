// @vitest-environment jsdom
/**
 * The diagram header offers Sync to model, Delete and Promote as the permission answer allows each
 * operation: on a read-only backend every write is refused, and the three are disabled with the reason.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { createApp, h, nextTick, type App } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { DiagramDetail } from '../../../domain'
import DiagramDetailHeader from '../DiagramDetailHeader.vue'
import { answered } from '../../composables/__tests__/permissionFixtures'

const WRITES = ['diagrams_sync_diagram_to_model', 'diagrams_delete_diagram', 'promotion_execute_promotion']

const LANDSCAPE: DiagramDetail = {
  artifact_id: 'ARC@1.a.landscape', artifact_type: 'diagram', name: 'Landscape', diagram_type: 'archimate-layered',
  version: '1.0.0', status: 'active', record_type: 'diagram', path: 'diagram-catalog/diagrams/landscape.puml',
  is_global: false, baseline_standing: { kind: 'enterprise-baseline' }, content_snippet: '', puml_source: '',
  revision: 'r1',
}

let app: App | null = null
afterEach(() => { app?.unmount(); app = null; document.body.innerHTML = '' })

const mounted = async (refused: readonly string[]) => {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:any(.*)*', component: { render: () => null } }] })
  app = answered(createApp({
    render: () => h(DiagramDetailHeader, {
      detail: LANDSCAPE, diagramId: 'ARC@1.a.landscape', editPath: '/diagram-edit',
      isGlobalDiagram: false, adminMode: false,
    }),
  }), refused, 'The backend is read-only')
  app.use(router)
  app.mount(host)
  await router.isReady()
  await nextTick()
  const button = (id: string) => host.querySelector<HTMLButtonElement>(`[data-testid="${id}"]`)!
  return { sync: button('diagram-sync'), remove: button('diagram-delete'), promote: button('diagram-promote') }
}

describe('the diagram header', () => {
  it('offers sync, delete and promote where they are permitted', async () => {
    const buttons = await mounted([])
    expect(Object.values(buttons).map((one) => one.disabled)).toEqual([false, false, false])
  })

  it('disables each with the reason where the permission answer refuses its write', async () => {
    const buttons = await mounted(WRITES)
    for (const one of Object.values(buttons)) {
      expect(one.disabled).toBe(true)
      expect(one.title).toBe('The backend is read-only')
    }
  })
})

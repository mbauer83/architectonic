// @vitest-environment jsdom
//
// *Lay out automatically…* (A-02.42): the picture the diagram would have beside the one it has, and on
// confirming, the diagram's own replacement with `manual_layout: false` — the save the canvas makes, from
// the membership the diagram states. A refusal is said in the dialog and nothing is reported laid out.

import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick, type App } from 'vue'
import { Effect } from 'effect'
import DiagramAutoLayoutDialog from '../DiagramAutoLayoutDialog.vue'
import { modelServiceKey } from '../../keys'
import type { ModelService } from '../../../application/ModelService'
import type { DiagramDetail } from '../../../domain'

const DETAIL = {
  artifact_id: 'ARC@1.a.goals', name: 'Goals', diagram_type: 'archimate-motivation', is_global: false,
  entity_ids_used: ['GOL@1.g'], connection_ids_used: ['GOL@1.g---OUT@2.o@@archimate-realization'],
  extra: { 'manual-layout': true },
} as unknown as DiagramDetail
const WRITE = { artifact_id: 'ARC@1.a.goals', path: 'x', content: null, verification: null, warnings: [] }
const PREVIEW = { puml: '', image: 'data:image/png;base64,AA==', warnings: [], derived_entities: null }

let app: App | null = null
let host: HTMLDivElement

const settle = async (): Promise<void> => {
  await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  await nextTick()
}

const mounted = (svc: Partial<ModelService>) => {
  const [laidOut, closed] = [vi.fn(), vi.fn()]
  host = document.createElement('div')
  document.body.appendChild(host)
  globalThis.URL.createObjectURL = () => 'blob:now'
  globalThis.URL.revokeObjectURL = () => undefined
  app = createApp({ render: () => h(DiagramAutoLayoutDialog, { detail: DETAIL, onLaidOut: laidOut, onClose: closed }) })
  app.provide(modelServiceKey, {
    getDiagramSvg: () => Effect.succeed('<svg xmlns="http://www.w3.org/2000/svg"/>'),
    previewDiagram: () => Effect.succeed(PREVIEW), ...svc,
  } as unknown as ModelService)
  app.mount(host)
  return { laidOut, closed }
}

const confirm = (): HTMLButtonElement => host.querySelector('[data-testid="auto-layout-confirm"]')!

afterEach(() => { app?.unmount(); app = null; host.remove() })

describe('laying a hand-written diagram out automatically', () => {
  it('shows both pictures and says the hand-written body is replaced', async () => {
    mounted({})
    await settle()
    const images = [...host.querySelectorAll('img')].map((img) => img.getAttribute('src'))
    expect(images).toEqual(['blob:now', PREVIEW.image])
    expect(host.textContent).toContain('The hand-written body is replaced')
  })

  it('writes the diagram\'s own replacement with manual_layout false, from what it states it draws', async () => {
    const editDiagram = vi.fn(() => Effect.succeed({ ...WRITE, wrote: true }))
    const { laidOut } = mounted({ editDiagram })
    await settle()
    confirm().click()
    await settle()
    expect(editDiagram).toHaveBeenCalledWith('ARC@1.a.goals', expect.objectContaining({
      diagram_type: 'archimate-motivation', name: 'Goals', entity_ids: ['GOL@1.g'],
      connection_ids: ['GOL@1.g---OUT@2.o@@archimate-realization'], manual_layout: false, dry_run: false,
    }))
    expect(laidOut).toHaveBeenCalledOnce()
  })

  it('says why when the write refuses, and reports nothing laid out', async () => {
    const editDiagram = vi.fn(() => Effect.succeed({ ...WRITE, wrote: false, warnings: ['E101 refused'] }))
    const { laidOut } = mounted({ editDiagram })
    await settle()
    confirm().click()
    await settle()
    expect(host.querySelector('[role="alert"]')?.textContent).toContain('E101 refused')
    expect(laidOut).not.toHaveBeenCalled()
  })
})

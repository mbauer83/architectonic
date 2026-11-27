// @vitest-environment jsdom
/**
 * The line under a diagram's title says who it is for and what it answers; a referenced element links to its
 * page, and lines taken from the applied viewpoint say so.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { createApp, h, nextTick, type App } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { DiagramPurpose } from '../../../domain/purposeLines'
import DiagramPurposeLine from '../DiagramPurposeLine.vue'

let app: App | null = null
afterEach(() => { app?.unmount(); app = null; document.body.innerHTML = '' })

const mounted = async (purpose: DiagramPurpose): Promise<HTMLElement> => {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:any(.*)*', component: { render: () => null } }] })
  app = createApp({ render: () => h(DiagramPurposeLine, { purpose }) })
  app.use(router)
  app.mount(host)
  await router.isReady()
  await nextTick()
  return host
}

describe('DiagramPurposeLine', () => {
  it('reads "For … · Answers …", linking each referenced element', async () => {
    const host = await mounted({
      stakeholders: [{ text: 'Operations', ref: 'STK@1.a' }, { text: 'Warehouse staff' }],
      concerns: [{ text: 'How fast is an order filled?' }],
    })

    const line = host.querySelector('[data-testid="diagram-purpose-line"]')!
    expect(line.textContent?.replace(/\s+/g, ' ').trim())
      .toBe('For Operations, Warehouse staff · Answers How fast is an order filled?')
    expect(host.querySelector('a')?.getAttribute('href')).toBe(`/entities/${encodeURIComponent('STK@1.a')}`)
  })

  it('names the viewpoint a shown list came from', async () => {
    const host = await mounted({ stakeholders: [{ text: 'Architects' }], concerns: [], inherited_from: 'layered' })

    expect(host.textContent).toContain('(from viewpoint layered)')
    expect(host.textContent).not.toContain('Answers')
  })
})

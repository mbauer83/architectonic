// @vitest-environment jsdom
//
// The promotion dry run shows the open advice on what it would carry, apart from what blocks it.

import { afterEach, describe, expect, it } from 'vitest'
import { createApp, defineComponent, h, nextTick, type App } from 'vue'
import PromotionAdviceList from '../PromotionAdviceList.vue'
import type { VerificationIssue } from '../../../domain/schemas/write-results'

const RouterLinkStub = defineComponent({
  props: { to: { type: Object, required: true } },
  setup: (_props, { slots }) => () => h('a', { class: 'link' }, slots.default?.()),
})

let app: App | null = null
let host: HTMLDivElement

const mount = async (advice: readonly VerificationIssue[]): Promise<HTMLDivElement> => {
  host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp({ render: () => h(PromotionAdviceList, { advice }) })
  app.component('RouterLink', RouterLinkStub)
  app.mount(host)
  await nextTick()
  return host
}

afterEach(() => { app?.unmount(); app = null; host.remove() })

describe('advice in the promotion dry run', () => {
  it('lists each advice with a link to its element and says it does not block', async () => {
    const root = await mount([{
      severity: 'advice', code: 'A341', message: 'nothing orders its parts',
      details: { artifact_id: 'PRC@1.a.handle-order', status: 'active' },
    }])

    const box = root.querySelector('[data-testid="promotion-advice"]')
    expect(box?.textContent).toContain('do not block the promotion')
    expect(box?.querySelector('.link')?.textContent?.trim()).toBe('nothing orders its parts')
  })

  it('is absent when there is no advice', async () => {
    const root = await mount([])

    expect(root.querySelector('[data-testid="promotion-advice"]')).toBeNull()
  })
})

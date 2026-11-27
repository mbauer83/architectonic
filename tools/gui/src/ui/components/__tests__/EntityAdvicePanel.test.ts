// @vitest-environment jsdom
//
// Advice on the entity page is as loud as the element's status says: on a draft a small marker with a
// count and no list in view, on an active element each finding listed with its reason. An accepted one
// is shown as "Accepted: …" in its place, and accepting or withdrawing emits the set to store.

import { afterEach, describe, expect, it } from 'vitest'
import { createApp, h, nextTick, type App } from 'vue'
import EntityAdvicePanel from '../EntityAdvicePanel.vue'
import { acknowledging, adviceCountLabel, hasAReason, withdrawing } from '../entityAdvice'
import type { EntityAdvice } from '../../../domain/schemas/entities'

const OPEN = {
  severity: 'advice' as const,
  code: 'A341',
  message: "'Handle Order' is a process, an ordered sequence, but nothing orders its 2 composed parts",
  details: { artifact_id: 'PRC@1.a.handle-order', status: 'draft', parts: ['a', 'b'] },
}

let app: App | null = null
let host: HTMLDivElement
let emitted: unknown[] = []

const mount = async (advice: EntityAdvice): Promise<HTMLDivElement> => {
  emitted = []
  host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp({
    render: () => h(EntityAdvicePanel, { advice, onAcknowledge: (entries: unknown) => emitted.push(entries) }),
  })
  app.mount(host)
  await nextTick()
  return host
}

afterEach(() => { app?.unmount(); app = null; host.remove() })

describe('advice by status', () => {
  it('is a small marker with a count on a draft, not a listing', async () => {
    const root = await mount({ presentation: 'marker', open: [OPEN], accepted: [] })

    const marker = root.querySelector('[data-testid="advice-marker"]')
    expect(marker?.tagName).toBe('DETAILS')
    expect(marker?.hasAttribute('open')).toBe(false)
    expect(root.querySelector('.marker-summary')?.textContent?.trim()).toBe('1 advice')
    expect(root.querySelector('[data-testid="advice-list"]')).toBeNull()
  })

  it('is listed with its reason on an active element', async () => {
    const root = await mount({ presentation: 'listed', open: [OPEN], accepted: [] })

    const list = root.querySelector('[data-testid="advice-list"]')
    expect(list).not.toBeNull()
    expect(list?.textContent).toContain('nothing orders its 2 composed parts')
    expect(root.querySelector('[data-testid="advice-marker"]')).toBeNull()
  })

  it('shows an accepted advice as "Accepted: …" in its place', async () => {
    const root = await mount({
      presentation: 'listed', open: [], accepted: [{ code: 'A341', title: 'unordered', reason: 'A checklist.' }],
    })

    expect(root.querySelector('[data-testid="advice-accepted"]')?.textContent).toContain('Accepted: A checklist.')
    expect(root.querySelector('[data-testid="advice-list"]')).toBeNull()
  })

  it('renders nothing when there is nothing to say', async () => {
    const root = await mount({ presentation: 'listed', open: [], accepted: [] })

    expect(root.querySelector('[data-testid="entity-advice"]')).toBeNull()
  })

  it('emits the acknowledgement set when an advice is accepted with a reason', async () => {
    const root = await mount({ presentation: 'listed', open: [OPEN], accepted: [] })

    ;(root.querySelector('.advice-item .btn-link') as HTMLButtonElement).click()
    await nextTick()
    const input = root.querySelector('.accept-reason') as HTMLInputElement
    input.value = '  A checklist.  '
    input.dispatchEvent(new Event('input'))
    await nextTick()
    ;(root.querySelector('.accept-form') as HTMLFormElement).dispatchEvent(new Event('submit'))
    await nextTick()

    expect(emitted).toEqual([[{ code: 'A341', reason: 'A checklist.' }]])
  })
})

describe('the acknowledgement set an edit sends', () => {
  const stored = [{ code: 'A341', title: 't', reason: 'old' }]

  it('replaces an earlier acknowledgement of the same code', () => {
    expect(acknowledging(stored, 'A341', ' new ')).toEqual([{ code: 'A341', reason: 'new' }])
  })

  it('withdraws one, leaving the rest', () => {
    expect(withdrawing(stored, 'A341')).toEqual([])
  })

  it('counts without listing', () => {
    expect(adviceCountLabel(1)).toBe('1 advice')
    expect(adviceCountLabel(3)).toBe('3 advice')
  })

  it('needs a reason', () => {
    expect(hasAReason('   ')).toBe(false)
    expect(hasAReason('deliberate')).toBe(true)
  })
})

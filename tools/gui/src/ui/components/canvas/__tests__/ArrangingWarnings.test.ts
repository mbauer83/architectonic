// @vitest-environment jsdom
//
// "⚠ hidden behind …" names what covers an element as the list of changes names it: by its name in the
// model, where the page knows it, rather than by the label the picture draws, which carries «Type».

import { afterEach, describe, expect, it } from 'vitest'
import { createApp, h, shallowRef, type App } from 'vue'
import ArrangingWarnings from '../ArrangingWarnings.vue'
import type { ArrangementSession } from '../../../composables/useArrangementSession'

let app: App | null = null
afterEach(() => { app?.unmount(); app = null })

const session = () => ({
  geometry: shallowRef({
    elements: [
      { alias: 'A', label: 'Index Repository «Application Component»' },
      { alias: 'B', label: 'Write Request Queue «Module»' },
    ],
    boxes: [],
    relations: [],
  }),
  placement: shallowRef({
    elements: new Map([
      ['A', { left: 0, top: 0, right: 100, bottom: 50 }],
      ['B', { left: 20, top: 10, right: 120, bottom: 60 }],
    ]),
    boxes: new Map(),
  }),
  breaches: shallowRef([]),
}) as unknown as ArrangementSession

const marked = (nameOf?: (alias: string) => string) => {
  const host = document.createElement('div')
  app = createApp({
    render: () => h('svg', [h(ArrangingWarnings, { session: session(), order: ['A', 'B'], pixel: 1, nameOf })]),
  })
  app.mount(host)
  return host.querySelector('[data-mark="hidden:A"]')?.textContent?.trim()
}

describe('what an element is hidden behind', () => {
  it('is named by its name in the model where the page gives one', () => {
    expect(marked((alias) => (alias === 'B' ? 'Write Request Queue' : alias))).toBe('⚠ hidden behind Write Request Queue')
  })

  it('falls back to the label the picture draws where none is given', () => {
    expect(marked()).toBe('⚠ hidden behind Write Request Queue «Module»')
  })
})

// @vitest-environment jsdom
/**
 * Check layout in the edit bar (owner): a quiet control, off until asked for. Off, it says nothing about
 * breaches and asks for none; on, it shows how many there are beside it and names each in its tooltip.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { computed, createApp, h, nextTick, ref, type App } from 'vue'
import type { Breach } from '../../../domain/layout/lab/labBreaches'
import type { DiagramEditMode } from '../../composables/useDiagramEditMode'
import DiagramEditBar from '../DiagramEditBar.vue'

const geometry = {
  elements: [{ alias: 'A', label: 'Order System' }, { alias: 'B', label: 'Billing' }],
  boxes: [],
  relations: [{ index: 0, source: 'A', target: 'B' }],
}

const breach = (rule: Breach['rule'], at: Breach['at'] = []): Breach => ({ relation: 0, rule, tier: 'hard', at })

let app: App | null = null
afterEach(() => { app?.unmount(); app = null })

const mounted = (breaches: readonly Breach[]) => {
  let asked = 0
  const checking = ref(false)
  const edit = {
    session: {
      state: ref({ byHand: true }),
      geometry: ref(geometry),
      breaches: computed(() => { asked += 1; return breaches }),
      undo: () => undefined,
      redo: () => undefined,
    },
    editing: {
      changes: ref([]), saving: ref(false), error: ref(null),
      returnToAutomatic: () => undefined, discard: () => undefined, save: () => Promise.resolve(true),
    },
    leaving: ref(false),
    canUndo: ref(false),
    canRedo: ref(false),
    checking,
    toggleCheck: () => { checking.value = !checking.value },
    panel: { open: ref(false), toggle: () => undefined },
    keepEditing: () => undefined,
  } as unknown as DiagramEditMode
  const host = document.createElement('div')
  app = createApp({ render: () => h(DiagramEditBar, { edit }) })
  app.mount(host)
  return { host, edit, asked: () => asked }
}

describe('check layout', () => {
  it('is off until asked for, and off shows no count and reads no breaches', () => {
    const { host, asked } = mounted([breach('ends-overlap')])
    const control = host.querySelector('[data-testid="edit-check-layout"]')

    expect(control?.getAttribute('aria-pressed')).toBe('false')
    expect(host.querySelector('[data-testid="edit-check-count"]')).toBeNull()
    expect(asked()).toBe(0)
  })

  it('on, counts each breach once and names each in its tooltip', async () => {
    const twice = [{ x: 0, y: 0 }, { x: 10, y: 0 }]
    const { host } = mounted([breach('ends-overlap'), breach('jog', twice), breach('jog', twice)])
    const control = host.querySelector<HTMLButtonElement>('[data-testid="edit-check-layout"]')

    control?.click()
    await nextTick()

    expect(control?.getAttribute('aria-pressed')).toBe('true')
    expect(host.querySelector('[data-testid="edit-check-count"]')?.textContent).toBe('2')
    expect(control?.getAttribute('title')?.split('\n')).toEqual([
      'Order System → Billing joins two elements drawn over each other',
      'Order System → Billing jogs',
    ])
  })

  it('on with nothing broken, says so', async () => {
    const { host } = mounted([])
    const control = host.querySelector<HTMLButtonElement>('[data-testid="edit-check-layout"]')

    control?.click()
    await nextTick()

    expect(host.querySelector('[data-testid="edit-check-count"]')?.textContent).toBe('0')
    expect(control?.getAttribute('title')).toBe('No layout rule is broken')
  })
})

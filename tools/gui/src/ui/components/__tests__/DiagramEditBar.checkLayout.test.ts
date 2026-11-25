// @vitest-environment jsdom
/**
 * Check layout in the edit bar (owner): a quiet control, off until asked for. Off, it says nothing about
 * breaches and asks for none; on, it shows how many there are beside it and names each in its tooltip.
 * And what the bar says of the session (01·6): Undo names its step, and the count names the model's share.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { computed, createApp, h, nextTick, ref, type App } from 'vue'
import type { Breach } from '../../../domain/layout/lab/labBreaches'
import type { DiagramEditMode } from '../../composables/useDiagramEditMode'
import DiagramEditBar from '../DiagramEditBar.vue'
import type { AuthoredGrouping } from '../../../domain/authoredGrouping'

const geometry = {
  elements: [{ alias: 'A', label: 'Order System' }, { alias: 'B', label: 'Billing' }],
  boxes: [],
  relations: [{ index: 0, source: 'A', target: 'B' }],
}

const breach = (rule: Breach['rule'], at: Breach['at'] = []): Breach => ({ relation: 0, rule, tier: 'hard', at })

let app: App | null = null
afterEach(() => { app?.unmount(); app = null })

interface Change { readonly key: string; readonly text: string; readonly model?: boolean }

const mounted = (
  breaches: readonly Breach[], changes: readonly Change[] = [], undoStep: string | null = null,
  stated: readonly AuthoredGrouping[] = [],
) => {
  let asked = 0
  const checking = ref(false)
  const session = {
    state: ref({ byHand: true }),
    geometry: ref(geometry),
    breaches: computed(() => { asked += 1; return breaches }),
    undo: () => undefined,
    redo: () => undefined,
  }
  const edit = {
    session,
    editing: {
      session, statedGroupings: () => stated, restate: () => Promise.resolve(true),
      changes: ref(changes), saving: ref(false), error: ref(null),
      undoStep: ref(undoStep), redoStep: ref(null),
      returnToAutomatic: () => undefined, discard: () => undefined, save: () => Promise.resolve(true),
    },
    leaving: ref(false),
    canUndo: ref(undoStep !== null),
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

describe('what the bar says of the session', () => {
  it("names the step Undo would take, and says there is none to redo", () => {
    const { host } = mounted([], [], 'Removed from the diagram: Billing — it stays in the model')
    expect(host.querySelector('[data-testid="edit-undo"]')?.getAttribute('title'))
      .toBe('Undo: Removed from the diagram: Billing — it stays in the model (Ctrl+Z)')
    expect(host.querySelector('[data-testid="edit-redo"]')?.getAttribute('title')).toBe('Nothing to redo')
  })

  it('names how many changes go to the model, and lists them under Model and Diagram', async () => {
    const { host } = mounted([], [
      { key: 'r', text: 'Create relationship: Order System — serving → Billing', model: true },
      { key: 'A', text: 'Arranged: Order System' },
    ])
    const count = host.querySelector<HTMLButtonElement>('[data-testid="change-count"]')
    expect(count?.textContent?.replace(/\s+/g, ' ').trim()).toBe('2 changes · 1 to the model ▾')
    count?.click()
    await nextTick()
    expect(host.querySelector('[data-testid="change-group-model"]')?.textContent).toContain('1 change to the model')
    expect(host.querySelector('[data-testid="change-group-diagram"]')?.textContent).toContain('1 change to this diagram')
  })
})

describe('the boxes the bar offers back', () => {
  it('offers Return to automatic boxes only while the diagram states layer or type boxes of its own', () => {
    const offered = (stated: readonly AuthoredGrouping[]) =>
      mounted([], [], null, stated).host.querySelector('[data-testid="return-to-automatic-boxes"]') !== null
    expect(offered([])).toBe(false)
    expect(offered([{ id: 'g-Front1', label: 'Front office', 'entity-ids': ['APP@1.a'] }])).toBe(false)
    expect(offered([{ id: 'g-Biz1', label: 'Business', 'entity-ids': [], rule: { domain: 'business' } }])).toBe(true)
  })
})

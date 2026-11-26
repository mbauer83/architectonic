// @vitest-environment jsdom
/**
 * Discard in the edit bar asks before it throws anything away, in the bar's own question: the count
 * named, Cancel holding the focus so Enter on arrival keeps everything, and Discard beside it.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { computed, createApp, defineComponent, h, nextTick, ref, type App } from 'vue'
import type { DiagramEditMode } from '../../composables/useDiagramEditMode'
import { useEditSessionExits } from '../../composables/useEditSessionExits'
import DiagramEditBar from '../DiagramEditBar.vue'

let app: App | null = null
afterEach(() => { app?.unmount(); app = null; document.body.replaceChildren() })

const mounted = (changes: readonly { key: string; text: string }[]) => {
  const discarded: string[] = []
  let leave!: () => void
  const pending = ref(changes)
  const session = {
    state: ref({ byHand: false }), geometry: ref(null), breaches: computed(() => []),
    undo: () => undefined, redo: () => undefined,
  }
  const host = document.createElement('div')
  document.body.append(host)
  app = createApp(defineComponent({
    setup() {
      const exits = useEditSessionExits({
        unsaved: () => pending.value.length > 0,
        save: () => Promise.resolve(true),
        discard: () => { discarded.push('discard'); pending.value = [] },
        close: () => undefined,
      })
      leave = () => exits.done()
      const edit = {
        ...exits,
        session,
        editing: {
          session, statedGroupings: () => [], restate: () => Promise.resolve(true), reference: () => null,
          changes: pending, saving: ref(false), error: ref(null), stale: ref(false), undoStep: ref(null), redoStep: ref(null),
          returnToAutomatic: () => undefined, discard: () => undefined, save: () => Promise.resolve(true),
        },
        canUndo: ref(true), canRedo: ref(false), checking: ref(false), toggleCheck: () => undefined,
        panel: { open: ref(false), toggle: () => undefined },
      } as unknown as DiagramEditMode
      return () => h(DiagramEditBar, { edit })
    },
  }))
  app.mount(host)
  const find = (id: string) => host.querySelector<HTMLButtonElement>(`[data-testid="${id}"]`)
  return { find, discarded, leave: () => leave() }
}

const TWO = [{ key: 'A', text: 'Arranged: Order System' }, { key: 'B', text: 'Arranged: Billing' }]

describe('Discard', () => {
  it('asks first, naming what goes, with Cancel focused', async () => {
    const { find, discarded } = mounted(TWO)
    find('edit-discard')?.click()
    await nextTick()

    expect(find('discard-choice')?.textContent).toContain('Discard 2 changes?')
    expect(document.activeElement).toBe(find('discard-cancel'))
    expect(discarded).toEqual([])
  })

  it('Cancel keeps the changes and gives the bar back', async () => {
    const { find, discarded } = mounted(TWO)
    find('edit-discard')?.click()
    await nextTick()
    find('discard-cancel')?.click()
    await nextTick()

    expect(find('discard-choice')).toBeNull()
    expect(find('edit-discard')).not.toBeNull()
    expect(discarded).toEqual([])
  })

  it('Discard, confirmed, throws the changes away', async () => {
    const { find, discarded } = mounted(TWO)
    find('edit-discard')?.click()
    await nextTick()
    find('discard-confirm')?.click()
    await nextTick()

    expect(discarded).toEqual(['discard'])
    expect(find('discard-choice')).toBeNull()
  })
})

describe('the leave question', () => {
  it('starts on Save and exit, its safest answer', async () => {
    const { find, leave } = mounted(TWO)
    leave()
    await nextTick()

    expect(find('leave-choice')?.textContent).toContain('2 unsaved')
    expect(document.activeElement).toBe(find('save-and-exit'))
  })
})

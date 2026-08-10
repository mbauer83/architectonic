// @vitest-environment jsdom
/**
 * Panning and selecting share the primary button, so every assertion here is about which of the
 * two a given press turned out to be.
 *
 * The regression that prompted it: both diagram viewports declined to pan whenever the press
 * landed on a selectable element, which made every model entity a dead zone. Only the auto-created
 * grouping boxes — the one thing on an ArchiMate view carrying no entity id — could still be
 * dragged, so the denser the diagram the less of it could be moved.
 */

import { describe, expect, it, vi, afterEach } from 'vitest'
import { createApp, defineComponent, ref, type Ref } from 'vue'
import { usePanGesture } from '../usePanGesture'

/** `usePanGesture` registers `onUnmounted`, so it is exercised where that means something. */
const mounted = <T>(setup: () => T): { value: T; unmount: () => void } => {
  let value!: T
  const app = createApp(defineComponent({ setup() { value = setup(); return () => null } }))
  app.mount(window.document.createElement('div'))
  return { value, unmount: () => app.unmount() }
}

interface Harness {
  entity: HTMLElement
  button: HTMLElement
  tx: Ref<number>
  ty: Ref<number>
  selected: string[]
  unmount: () => void
}

const harness = (): Harness => {
  const container = window.document.createElement('div')
  const entity = window.document.createElement('div')
  entity.setAttribute('data-entity-id', 'APP@1.aaaaaa.the-thing')
  const button = window.document.createElement('button')
  container.append(entity, button)
  window.document.body.append(container)

  const tx = ref(0)
  const ty = ref(0)
  const { value, unmount } = mounted(() => usePanGesture(tx, ty))
  container.addEventListener('mousedown', value.onMouseDown)

  const selected: string[] = []
  entity.addEventListener('click', () => selected.push('entity'))
  return { entity, button, tx, ty, selected, unmount }
}

afterEach(() => {
  window.document.body.replaceChildren()
  vi.useRealTimers()
})

const press = (element: Element, x: number, y: number, button = 0) =>
  element.dispatchEvent(new MouseEvent('mousedown', {
    bubbles: true, cancelable: true, button, clientX: x, clientY: y,
  }))
const moveTo = (x: number, y: number) =>
  window.dispatchEvent(new MouseEvent('mousemove', { clientX: x, clientY: y }))
const release = () => window.dispatchEvent(new MouseEvent('mouseup'))
const click = (element: Element) =>
  element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))

describe('a press that travels', () => {
  it('pans even when it started on a model entity — the regression', () => {
    const { entity, tx, ty } = harness()

    press(entity, 100, 100)
    moveTo(140, 70)

    expect([tx.value, ty.value]).toEqual([40, -30])
  })

  it('tracks the pointer from where the press started, not from where the threshold was crossed', () => {
    const { entity, tx } = harness()

    press(entity, 100, 100)
    moveTo(105, 100) // first move past the threshold
    moveTo(150, 100)

    expect(tx.value).toBe(50)
  })

  it('does not also select what it started on', () => {
    const { entity, selected } = harness()

    press(entity, 100, 100)
    moveTo(160, 100)
    release()
    click(entity)

    expect(selected).toEqual([])
  })

  it('swallows only that one click, not the next honest one', () => {
    const { entity, selected } = harness()

    press(entity, 100, 100)
    moveTo(160, 100)
    release()
    click(entity)
    click(entity)

    expect(selected).toEqual(['entity'])
  })

  it('leaves nothing armed when no click follows the release at all', () => {
    vi.useFakeTimers()
    const { entity, selected } = harness()

    press(entity, 100, 100)
    moveTo(160, 100)
    release()
    // The pointer left the window, so the browser never dispatched the click this pan would have
    // produced. Without the disarm, the *next* unrelated click anywhere would be eaten instead.
    vi.advanceTimersByTime(1)
    click(entity)

    expect(selected).toEqual(['entity'])
  })
})

describe('a press that stays put', () => {
  it('is a click, and reaches what it landed on', () => {
    const { entity, tx, ty, selected } = harness()

    press(entity, 100, 100)
    moveTo(102, 101) // hand jitter, under the threshold
    release()
    click(entity)

    expect([tx.value, ty.value]).toEqual([0, 0])
    expect(selected).toEqual(['entity'])
  })
})

describe('a press the viewport has no claim on', () => {
  it('ignores a control that owns its own press', () => {
    const { button, tx } = harness()

    press(button, 100, 100)
    moveTo(200, 100)

    expect(tx.value).toBe(0)
  })

  it('ignores a non-primary button, which is a context menu rather than a pan', () => {
    const { entity, tx } = harness()

    press(entity, 100, 100, 2)
    moveTo(200, 100)

    expect(tx.value).toBe(0)
  })
})

describe('after the viewport goes away', () => {
  it('stops moving anything', () => {
    const { entity, tx, unmount } = harness()

    press(entity, 100, 100)
    unmount()
    moveTo(200, 100)

    expect(tx.value).toBe(0)
  })
})

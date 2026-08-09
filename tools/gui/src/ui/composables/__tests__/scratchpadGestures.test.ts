// @vitest-environment jsdom
/**
 * Who owns the pointer while a gesture is running.
 *
 * The browser suite found this one and could not have been talked out of it: a drag recorded no
 * write at all, because the note panel is an absolutely positioned *sibling* of the viewport and
 * the cursor crossing it fired `pointerleave`. Ending a gesture there meant a note dragged toward
 * the top-left of its own canvas stopped following the cursor a third of the way across.
 *
 * These assert the fix's mechanism rather than its symptom: the gesture takes the pointer, so no
 * overlay can interrupt it, and it gives it back when the button comes up.
 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { useScratchpadGestures } from '../useScratchpadGestures'

const NOTE_BOX = { width: 132, height: 120 }

afterEach(() => { vi.restoreAllMocks() })

/** Only the fields the gestures read. jsdom has no `PointerEvent`, and a shim of the whole
 * interface would assert more about the polyfill than about the canvas. */
const press = (x: number, y: number, pointerId = 7): PointerEvent => ({
  clientX: x,
  clientY: y,
  pointerId,
  shiftKey: false,
  ctrlKey: false,
  metaKey: false,
  target: null,
  stopPropagation: vi.fn(),
  preventDefault: vi.fn(),
} as unknown as PointerEvent)

const intents = () => ({
  onSelect: vi.fn(),
  onMoveNote: vi.fn(),
  onCreateNote: vi.fn(),
  onLinkNotes: vi.fn(),
  onOpenMenu: vi.fn(),
})

/** A viewport that reports a rectangle and records what is captured on it. jsdom implements
 * neither `getBoundingClientRect` with real geometry nor pointer capture at all. */
const canvas = () => {
  const element = window.document.createElement('div')
  element.getBoundingClientRect = () =>
    ({ left: 0, top: 0, width: 1000, height: 700 }) as DOMRect
  const captured = vi.fn()
  const released = vi.fn()
  element.setPointerCapture = captured
  element.releasePointerCapture = released
  const on = intents()
  const gestures = useScratchpadGestures(ref(element), () => ({ x: 100, y: 100 }), NOTE_BOX, on)
  return { element, captured, released, on, gestures }
}

describe('a gesture on the canvas', () => {
  it('takes the pointer when a note starts being dragged, and gives it back on release', () => {
    const { captured, released, gestures } = canvas()

    gestures.onNotePointerDown(press(300, 260), 'n1')
    expect(captured).toHaveBeenCalledWith(7)

    gestures.onPointerUp(press(420, 320))
    expect(released).toHaveBeenCalledWith(7)
  })

  it('takes the pointer for a pan and for drawing a link too', () => {
    const panning = canvas()
    panning.gestures.onBackgroundPointerDown(press(300, 260))
    expect(panning.captured).toHaveBeenCalledWith(7)

    const linking = canvas()
    linking.gestures.onHandlePointerDown(press(300, 260), 'n1')
    expect(linking.captured).toHaveBeenCalledWith(7)
  })

  it('keeps moving the note after the cursor has left the viewport, which is the defect', () => {
    const { on, gestures } = canvas()

    gestures.onNotePointerDown(press(300, 260), 'n1')
    // Where the note panel sits: over the canvas's top-left corner and outside its element. The
    // pointer is captured, so this arrives at the viewport regardless — and must still move a note.
    gestures.onPointerMove(press(200, 220))

    expect(on.onMoveNote).toHaveBeenCalledWith('n1', 0, 60)
  })

  it('drops a link on whatever is under the cursor, not on what the event was dispatched to', () => {
    const { on, gestures } = canvas()
    const note = window.document.createElement('article')
    note.dataset.noteId = 'n2'
    // jsdom does no layout, so it has no `elementFromPoint` to spy on; it is defined rather than
    // stubbed, which is also what says the production code reads the document and not the event.
    Object.defineProperty(window.document, 'elementFromPoint', {
      configurable: true, value: () => note,
    })

    gestures.onHandlePointerDown(press(300, 260), 'n1')
    gestures.onPointerUp(press(600, 400))

    expect(on.onLinkNotes).toHaveBeenCalledWith('n1', 'n2')
  })

  it('survives a browser that will not capture, rather than refusing the gesture', () => {
    const { element, on, gestures } = canvas()
    element.setPointerCapture = () => { throw new DOMException('no such pointer', 'NotFoundError') }

    gestures.onNotePointerDown(press(300, 260), 'n1')
    gestures.onPointerMove(press(360, 300))

    expect(on.onMoveNote).toHaveBeenCalledWith('n1', 160, 140)
  })
})

/**
 * The binding itself, asserted against the template: the suite mounts nothing, and the whole defect
 * was one handler on one element. A composable test cannot see it.
 */
describe('the canvas viewport', () => {
  const template = readFileSync(resolve(__dirname, '../../components/ScratchpadCanvas.vue'), 'utf8')

  it('ends a gesture on pointercancel and never on pointerleave', () => {
    expect(template).toContain('@pointercancel="onPointerUp"')
    expect(template).not.toContain('@pointerleave')
  })
})

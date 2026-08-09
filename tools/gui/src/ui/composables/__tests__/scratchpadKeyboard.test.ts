// @vitest-environment jsdom
/**
 * The canvas without a pointer.
 *
 * Asserted here rather than left to the browser suite because the interesting cases are the ones a
 * smoke test would never think to press: the context-menu key, `Shift+F10`, and a key arriving
 * while a title is being edited — where every one of these must stand aside.
 */

import { describe, expect, it, vi } from 'vitest'
import { isAdditive, noteKeydown, selectionAnnouncement } from '../useScratchpadKeyboard'

const intents = () => ({
  onToggle: vi.fn(),
  onEditTitle: vi.fn(),
  onDelete: vi.fn(),
  onMenu: vi.fn(),
  onClearSelection: vi.fn(),
})

const press = (key: string, extra: Partial<KeyboardEventInit> & { editing?: boolean } = {}) => {
  const { editing, ...init } = extra
  const event = new KeyboardEvent('keydown', { key, cancelable: true, ...init })
  const target = window.document.createElement('div')
  // jsdom does not derive `isContentEditable` from the attribute, and that property is what the
  // guard reads — so it is set directly rather than asserted against a shim that never fires.
  if (editing) Object.defineProperty(target, 'isContentEditable', { value: true })
  Object.defineProperty(event, 'target', { value: target })
  return event
}

describe('a focused note', () => {
  it('toggles its selection on Space, which is what a listbox option does', () => {
    const on = intents()

    noteKeydown(press(' '), 'n1', on)

    expect(on.onToggle).toHaveBeenCalledWith('n1', true)
  })

  it('enters its title on Enter and on F2', () => {
    const on = intents()

    noteKeydown(press('Enter'), 'n1', on)
    noteKeydown(press('F2'), 'n1', on)

    expect(on.onEditTitle).toHaveBeenCalledTimes(2)
  })

  it('opens the canvas menu on the context-menu key and on Shift+F10', () => {
    const on = intents()

    noteKeydown(press('ContextMenu'), 'n1', on)
    noteKeydown(press('F10', { shiftKey: true }), 'n1', on)

    expect(on.onMenu).toHaveBeenCalledTimes(2)
  })

  it('clears the selection on Escape and deletes on Delete', () => {
    const on = intents()

    noteKeydown(press('Escape'), 'n1', on)
    noteKeydown(press('Delete'), 'n1', on)

    expect(on.onClearSelection).toHaveBeenCalledOnce()
    expect(on.onDelete).toHaveBeenCalledWith('n1')
  })

  it('stands aside entirely while the title is being edited', () => {
    // Otherwise a space in a title would toggle the note and never reach the text.
    const on = intents()

    for (const key of [' ', 'Enter', 'Delete', 'Escape', 'ContextMenu']) {
      noteKeydown(press(key, { editing: true }), 'n1', on)
    }

    expect(Object.values(on).every((spy) => spy.mock.calls.length === 0)).toBe(true)
  })
})

describe('adding to a selection', () => {
  it('is Shift everywhere, which is what every canvas tool already trains', () => {
    expect(isAdditive({ shiftKey: true, ctrlKey: false, metaKey: false })).toBe(true)
    expect(isAdditive({ shiftKey: false, ctrlKey: false, metaKey: false })).toBe(false)
  })

  it('accepts the platform meta key, so Cmd works where Ctrl-click is the context menu', () => {
    expect(isAdditive({ shiftKey: false, ctrlKey: false, metaKey: true })).toBe(true)
  })
})

describe('what a screen reader is told', () => {
  it('names the count, and says so when there is none', () => {
    expect(selectionAnnouncement(0)).toBe('Nothing selected')
    expect(selectionAnnouncement(1)).toBe('1 note selected')
    expect(selectionAnnouncement(4)).toBe('4 notes selected')
  })
})

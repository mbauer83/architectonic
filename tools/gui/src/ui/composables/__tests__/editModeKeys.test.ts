/**
 * The keys of edit mode read as their commands (sketch 02·9): letters by the character they type, so
 * the same on QWERTY and QWERTZ; Shift makes an arrow fine and Alt makes it resize; Tab and Enter,
 * Ctrl+A and R are the canvas's.
 */
import { describe, expect, it } from 'vitest'
import { editKeyOf } from '../editModeKeys'

const key = (k: string, more: Partial<KeyboardEvent> = {}) =>
  ({ key: k, ctrlKey: false, metaKey: false, shiftKey: false, altKey: false, ...more })

describe('the keys of edit mode', () => {
  it('read undo, redo and select all with Ctrl or Cmd', () => {
    expect(editKeyOf(key('z', { ctrlKey: true }))).toEqual({ kind: 'undo' })
    expect(editKeyOf(key('Z', { ctrlKey: true, shiftKey: true }))).toEqual({ kind: 'redo' })
    expect(editKeyOf(key('y', { metaKey: true }))).toEqual({ kind: 'redo' })
    expect(editKeyOf(key('a', { ctrlKey: true }))).toEqual({ kind: 'select-all' })
  })

  it('read an arrow with its direction, fine with Shift and a resize with Alt', () => {
    expect(editKeyOf(key('ArrowLeft'))).toEqual({ kind: 'arrow', direction: [-1, 0], fine: false, resize: false })
    expect(editKeyOf(key('ArrowDown', { shiftKey: true, altKey: true })))
      .toEqual({ kind: 'arrow', direction: [0, 1], fine: true, resize: true })
  })

  it('read Tab, Shift+Tab, Enter and Shift+Enter for the element focus', () => {
    expect(editKeyOf(key('Tab'))).toEqual({ kind: 'tab', forward: true })
    expect(editKeyOf(key('Tab', { shiftKey: true }))).toEqual({ kind: 'tab', forward: false })
    expect(editKeyOf(key('Enter', { shiftKey: true }))).toEqual({ kind: 'enter', toggle: true })
  })

  it('read R, F, Space, stacking and Delete', () => {
    expect(editKeyOf(key('r'))).toEqual({ kind: 'rectangle' })
    expect(editKeyOf(key('R', { shiftKey: true }))).toEqual({ kind: 'rectangle' })
    expect(editKeyOf(key('f'))).toEqual({ kind: 'frame' })
    expect(editKeyOf(key(' '))).toEqual({ kind: 'pan' })
    expect(editKeyOf(key('PageUp', { shiftKey: true }))).toEqual({ kind: 'restack', how: 'front' })
    expect(editKeyOf(key('Backspace'))).toEqual({ kind: 'delete' })
  })

  it('leave every other key alone, and a letter under Alt', () => {
    expect(editKeyOf(key('x'))).toBeNull()
    expect(editKeyOf(key('r', { altKey: true }))).toBeNull()
    expect(editKeyOf(key('c', { ctrlKey: true }))).toBeNull()
  })
})

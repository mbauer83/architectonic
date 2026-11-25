/**
 * An element's menu on the canvas (sketch 03·5), in the sketch's order: what changes the element first,
 * what reaches beyond it next, what removes last — the destructive entry at the bottom, in the danger
 * colour. Only entries whose operation the editor has are listed; one it does not have is left out
 * rather than shown and refused.
 */
import type { CanvasMenuItem } from './canvasMenu'
import type { CanvasWords } from './canvasWords'
import type { Restack } from '../../domain/layout/stacking'

export type ElementMenuChoice = 'rename' | 'details' | 'connect' | 'open' | 'remove' | 'delete' | `stack:${Restack}`

/** Stacking among siblings (02·7), with the keys that do the same on the selection. */
export const STACKING_ITEMS: readonly CanvasMenuItem[] = [
  { id: 'stack:front', label: 'Bring to front', shortcut: 'Shift+PgUp', divider: true },
  { id: 'stack:forward', label: 'Bring forward', shortcut: 'PgUp' },
  { id: 'stack:backward', label: 'Send backward', shortcut: 'PgDn' },
  { id: 'stack:back', label: 'Send to back', shortcut: 'Shift+PgDn' },
]

/** The restacking a menu entry or a key asks for; null for anything else. */
export const restackOf = (choice: string): Restack | null => {
  const how = choice.startsWith('stack:') ? choice.slice('stack:'.length) : ''
  return how === 'front' || how === 'forward' || how === 'backward' || how === 'back' ? how : null
}

/** The restacking a key on the canvas asks for: PgUp and PgDn step, with Shift they go to the end. */
export const restackKey = (event: Pick<KeyboardEvent, 'key' | 'shiftKey'>): Restack | null =>
  event.key === 'PageUp' ? (event.shiftKey ? 'front' : 'forward')
    : event.key === 'PageDown' ? (event.shiftKey ? 'back' : 'backward') : null

/** *drafted*: the element is created in this session, so it has no page to open until Save. */
export const elementMenuItems = (words: CanvasWords, drafted: boolean): readonly CanvasMenuItem[] => [
  { id: 'rename', label: 'Rename', hint: 'also a double-click on it', shortcut: 'F2' },
  {
    id: 'details', label: 'Edit details…',
    hint: drafted ? 'its form holds them until it is saved' : 'summary, status, keywords, specializations, attributes',
    disabled: drafted,
  },
  {
    id: 'connect', label: 'Connect to…',
    hint: 'pick the other element by name, then the relation; also drag from its edge',
  },
  {
    id: 'open', label: 'Open', hint: drafted ? 'it has no page until it is saved' : 'its page, in a new tab',
    disabled: drafted,
  },
  ...STACKING_ITEMS,
  ...words.removeEntry
    ? [{ id: 'remove', label: words.removeEntry, hint: words.removeHint, shortcut: words.removeKey, divider: true }]
    : [],
  { id: 'delete', label: words.deleteEntry, hint: words.deleteHint, danger: true, divider: true },
]

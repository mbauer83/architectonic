/**
 * An element's menu on the canvas (sketch 03·5), in the sketch's order: what changes the element first,
 * what reaches beyond it next, what removes last — the destructive entry at the bottom, in the danger
 * colour. Only entries whose operation the editor has are listed; one it does not have is left out
 * rather than shown and refused.
 */
import type { CanvasMenuItem } from './canvasMenu'
import type { CanvasWords } from './canvasWords'

export type ElementMenuChoice = 'rename' | 'connect' | 'open' | 'remove' | 'delete'

/** *drafted*: the element is created in this session, so it has no page to open until Save. */
export const elementMenuItems = (words: CanvasWords, drafted: boolean): readonly CanvasMenuItem[] => [
  { id: 'rename', label: 'Rename', hint: 'also a double-click on it', shortcut: 'F2' },
  {
    id: 'connect', label: 'Connect to…',
    hint: 'pick the other element by name, then the relation; also drag from its edge',
  },
  {
    id: 'open', label: 'Open', hint: drafted ? 'it has no page until it is saved' : 'its page, in a new tab',
    disabled: drafted,
  },
  ...words.removeEntry
    ? [{ id: 'remove', label: words.removeEntry, hint: words.removeHint, shortcut: words.removeKey, divider: true }]
    : [],
  { id: 'delete', label: words.deleteEntry, hint: words.deleteHint, danger: true, divider: true },
]

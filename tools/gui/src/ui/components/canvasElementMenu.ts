/**
 * An element's menu on the canvas (sketch 03·5), in the sketch's order: what changes the element first,
 * what reaches beyond it next, what removes last — the destructive entry at the bottom, in the danger
 * colour. Only entries whose operation the editor has are listed; one it does not have is left out
 * rather than shown and refused.
 */
import type { CanvasMenuItem } from './canvasMenu'
import type { CanvasWords } from './canvasWords'
import type { Restack } from '../../domain/layout/stacking'

export type ElementMenuChoice =
  | 'rename' | 'details' | 'connect' | 'nest' | 'unnest' | 'occurrence' | 'open' | 'remove' | 'delete' | 'discard'
  | `stack:${Restack}`

/** Stacking among siblings (02·7), with the keys that do the same on the selection. */
export const STACKING_ITEMS: readonly CanvasMenuItem[] = [
  { id: 'stack:front', label: 'Bring to front', shortcut: 'Shift+PgUp', divider: true, command: 'element.restack' },
  { id: 'stack:forward', label: 'Bring forward', shortcut: 'PgUp', command: 'element.restack' },
  { id: 'stack:backward', label: 'Send backward', shortcut: 'PgDn', command: 'element.restack' },
  { id: 'stack:back', label: 'Send to back', shortcut: 'Shift+PgDn', command: 'element.restack' },
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

/**
 * A draft created in this session and not saved is not yet in the model: it is discarded, which takes
 * it and everything the session proposed about it away, rather than removed or deleted (03·6).
 */
const DISCARD_ITEM: CanvasMenuItem = {
  id: 'discard', label: 'Discard this draft', hint: 'it was never saved; Undo brings it back', danger: true,
  divider: true, command: 'element.discard',
}

/** Taking a saved element off the view, and deleting it from the model, in the page's words. */
const removing = (words: CanvasWords): readonly CanvasMenuItem[] => [
  ...words.removeEntry
    ? [{
      id: 'remove', label: words.removeEntry, hint: words.removeHint, shortcut: words.removeKey, divider: true,
      command: 'element.remove' as const,
    }]
    : [],
  {
    id: 'delete', label: words.deleteEntry, hint: words.deleteHint, danger: true, divider: true,
    command: 'element.delete',
  },
]

/**
 * *drafted*: the element is created in this session, so it has no page to open until Save. *nestedIn*:
 * the label of the diagram's own box it is in, which *Take out* takes it out of. *drawsAgain*: the
 * diagram type draws an element more than once (ArchiMate's occurrences).
 */
export const elementMenuItems = (
  words: CanvasWords, drafted: boolean, nestedIn: string | null = null, drawsAgain = false,
): readonly CanvasMenuItem[] => [
  { id: 'rename', label: 'Rename', hint: 'also a double-click on it', shortcut: 'F2', command: 'element.rename' },
  {
    id: 'details', label: 'Edit details…', command: 'element.details',
    hint: drafted ? 'its form holds them until it is saved' : 'summary, status, keywords, specializations, attributes',
    disabled: drafted,
  },
  {
    id: 'connect', label: 'Connect to…', command: 'element.connect',
    hint: 'pick the other element by name, then the relation; also drag from its edge',
  },
  {
    id: 'open', label: 'Open', command: 'element.open',
    hint: drafted ? 'it has no page until it is saved' : 'its page, in a new tab',
    disabled: drafted,
  },
  {
    id: 'nest', label: 'Nest in…', command: 'element.nest',
    hint: 'a box (diagram only), or an element that may contain it (a model change)',
  },
  ...nestedIn === null ? [] : [{
    id: 'unnest', label: `Take out of ${nestedIn}`, hint: 'onto the box around it', command: 'element.unnest' as const,
  }],
  ...drawsAgain
    ? [{
      id: 'occurrence', label: 'Add another occurrence here', disabled: drafted, command: 'element.occurrence' as const,
      hint: drafted ? 'once it is saved' : 'the same element drawn again, where the menu was opened',
    }]
    : [],
  ...STACKING_ITEMS,
  ...drafted ? [DISCARD_ITEM] : removing(words),
]


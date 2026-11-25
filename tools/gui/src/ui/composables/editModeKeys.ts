/**
 * The keys of edit mode, each read as the command it names (sketch 02·9): letters by the character they
 * type (`event.key`), never by the key's position, so they are where the keycap says on any layout.
 * What a command then does is the edit mode's (`useDiagramEditMode`).
 */
import { restackKey } from '../components/canvasElementMenu'
import type { Restack } from '../../domain/layout/stacking'

/** An arrow key as the direction it moves in. */
const ARROWS: Readonly<Record<string, readonly [number, number]>> = {
  ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1],
}

export type EditKey =
  | { readonly kind: 'escape' | 'undo' | 'redo' | 'delete' | 'frame' | 'pan' | 'select-all' | 'rectangle' }
  /** An arrow: *fine* with Shift (one pixel), *resize* with Alt (the right and bottom edges, Q35). */
  | {
    readonly kind: 'arrow'; readonly direction: readonly [number, number]
    readonly fine: boolean; readonly resize: boolean
  }
  | { readonly kind: 'restack'; readonly how: Restack }
  | { readonly kind: 'tab'; readonly forward: boolean }
  | { readonly kind: 'enter'; readonly toggle: boolean }

type Keyed = Pick<KeyboardEvent, 'key' | 'ctrlKey' | 'metaKey' | 'shiftKey' | 'altKey'>

const withCommand = (event: Keyed, key: string): EditKey | null => {
  if (key === 'z') return { kind: event.shiftKey ? 'redo' : 'undo' }
  if (key === 'y') return { kind: 'redo' }
  return key === 'a' ? { kind: 'select-all' } : null
}

const plain = (event: Keyed, key: string): EditKey | null => {
  if (event.altKey) return null
  if (key === 'f') return { kind: 'frame' }
  if (key === 'r') return { kind: 'rectangle' }
  if (event.key === ' ') return { kind: 'pan' }
  if (event.key === 'Tab') return { kind: 'tab', forward: !event.shiftKey }
  return event.key === 'Enter' ? { kind: 'enter', toggle: event.shiftKey } : null
}

/** The command *event* names in edit mode, or null where it names none. */
export const editKeyOf = (event: Keyed): EditKey | null => {
  const key = event.key.toLowerCase()
  const command = event.ctrlKey || event.metaKey
  if (event.key === 'Escape') return { kind: 'escape' }
  if (command) return withCommand(event, key)
  if (event.key === 'Delete' || event.key === 'Backspace') return { kind: 'delete' }
  const direction = ARROWS[event.key]
  if (direction) return { kind: 'arrow', direction, fine: event.shiftKey, resize: event.altKey }
  const how = restackKey(event)
  return how !== null ? { kind: 'restack', how } : plain(event, key)
}

/**
 * The entries of a menu opened at a point on a canvas (sketch 03·5): a label, an optional one-line
 * hint under it, an optional key at the right, a divider before a new group, and the destructive entry
 * in the danger colour. `CanvasMenu.vue` draws them; how the keys walk them is here, apart from the DOM.
 */
import type { Permission } from '../../domain/permissions'
import type { CanvasCommandName } from './canvasCommands'

export interface CanvasMenuItem {
  /** What `choose` answers with. */
  readonly id: string
  readonly label: string
  /** One muted line under the label: what the entry does, or why it cannot. */
  readonly hint?: string
  /** The key that does the same from the canvas, shown at the right. */
  readonly shortcut?: string
  /** A rule above the entry: the first of a new group. */
  readonly divider?: boolean
  /** A muted caption above the entry, naming the group it opens (a submenu's "Source end · …"). */
  readonly caption?: string
  readonly danger?: boolean
  readonly disabled?: boolean
  /** The canvas command the entry is (`canvasCommands`): refused by the permission answer, it is disabled. */
  readonly command?: CanvasCommandName
  /** A `data-testid` for the entry, where a suite names it. */
  readonly testid?: string
  /** Extra attributes carried onto the entry, as a suite or a reader of it addresses it. */
  readonly attrs?: Readonly<Record<string, string | undefined>>
}

/**
 * Where focus goes from entry *at* of *count* on *key*: the arrows step and wrap, Home and End go to
 * the ends; null for a key that does not move. From nowhere (*at* below 0) Down lands on the first and
 * Up on the last.
 */
export const menuStep = (key: string, at: number, count: number): number | null => {
  if (count === 0) return null
  if (key === 'Home') return 0
  if (key === 'End') return count - 1
  if (key !== 'ArrowDown' && key !== 'ArrowUp') return null
  const step = key === 'ArrowDown' ? 1 : -1
  if (at < 0) return step > 0 ? 0 : count - 1
  return (at + step + count) % count
}

/**
 * *items* as the permission answer offers them: an entry whose command is refused is disabled, and its hint
 * says why instead of what it does (A-02.24).
 */
export const permitted = (
  items: readonly CanvasMenuItem[], permit: (command: CanvasCommandName) => Permission,
): readonly CanvasMenuItem[] => items.map((item) => {
  const answer = item.command === undefined ? null : permit(item.command)
  return answer === null || answer.allowed ? item : { ...item, disabled: true, hint: answer.reason }
})

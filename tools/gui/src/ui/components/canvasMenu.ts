/**
 * The entries of a menu opened at a point on a canvas (sketch 03·5): a label, an optional one-line
 * hint under it, an optional key at the right, a divider before a new group, and the destructive entry
 * in the danger colour. `CanvasMenu.vue` draws them; how the keys walk them is here, apart from the DOM.
 */

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

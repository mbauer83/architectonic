/**
 * The canvas, without a pointer.
 *
 * A canvas is the easiest surface in a product to build mouse-only and the least excusable one to
 * leave that way: this is the tier a newcomer is told to start on, so "start here" cannot mean
 * "start here if you can drag". Every gesture the pointer offers has a key here — select, add to a
 * selection, edit, delete, open the menu, lift — and the notes layer is a real `listbox`, so a
 * screen reader announces what is selected rather than leaving it to a CSS border.
 *
 * The one thing keys deliberately do *not* do is draw a link by dragging. Linking is expressed as
 * two selections and a command instead, which is both operable and less error-prone than a
 * simulated drag.
 */

/** `Ctrl+click` is the context-menu gesture on Apple platforms, so accepting it as "add to the
 * selection" there would toggle a note *and* open the menu on the same click. Cmd takes its place;
 * Shift works everywhere and is what every canvas tool already trains. */
const APPLE = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)

export function isAdditive(event: { shiftKey: boolean; ctrlKey: boolean; metaKey: boolean }): boolean {
  return event.shiftKey || (APPLE ? event.metaKey : event.ctrlKey || event.metaKey)
}

export interface NoteKeyIntents {
  readonly onToggle: (id: string, additive: boolean) => void
  readonly onEditTitle: (id: string) => void
  readonly onDelete: (id: string) => void
  /** Open the canvas menu anchored at this note rather than at a pointer that does not exist. */
  readonly onMenu: (id: string) => void
  readonly onClearSelection: () => void
}

/**
 * What a focused note does with a key press, following the multi-select listbox convention:
 * `Space` toggles, `Enter`/`F2` enters the title, `Escape` leaves the selection empty, and the
 * context-menu key (or `Shift+F10`, its keyboard-only spelling) opens the menu.
 */
export function noteKeydown(event: KeyboardEvent, noteId: string, intents: NoteKeyIntents): void {
  // A key pressed while the title is being edited belongs to the title.
  if ((event.target as HTMLElement | null)?.isContentEditable) return

  if (event.key === ' ' || event.key === 'Spacebar') {
    event.preventDefault()
    intents.onToggle(noteId, true)
    return
  }
  if (event.key === 'Enter' || event.key === 'F2') {
    event.preventDefault()
    intents.onEditTitle(noteId)
    return
  }
  if (event.key === 'Delete') {
    event.preventDefault()
    intents.onDelete(noteId)
    return
  }
  if (event.key === 'ContextMenu' || (event.key === 'F10' && event.shiftKey)) {
    event.preventDefault()
    intents.onMenu(noteId)
    return
  }
  if (event.key === 'Escape') {
    intents.onClearSelection()
  }
}

/** What the notes layer announces: the count, phrased so it is worth interrupting for once. */
export function selectionAnnouncement(count: number): string {
  if (count === 0) return 'Nothing selected'
  return `${count} note${count === 1 ? '' : 's'} selected`
}

/**
 * Where to draw the canvas menu when it was opened from the keyboard.
 *
 * Anchored just under the note that had focus, in viewport pixels, because a keyboard user has no
 * pointer for the menu to appear beneath — and a menu that opened in the corner would make the
 * person hunt for the thing they were already on.
 */
export function menuAnchorFor(viewport: HTMLElement | null, noteId: string): { x: number; y: number } {
  const box = viewport?.getBoundingClientRect()
  const rect = window.document
    .querySelector<HTMLElement>(`[data-note-id="${noteId}"]`)
    ?.getBoundingClientRect()
  return {
    x: Math.max(0, (rect?.left ?? 0) - (box?.left ?? 0)),
    y: Math.max(0, (rect?.bottom ?? 0) - (box?.top ?? 0)),
  }
}

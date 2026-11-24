/**
 * Where a selected line's menu opens (sketch 02·9): on a right press over the line, its handles or its
 * label; and, from the menu key or Shift+F10, at the middle of the line on screen.
 */

/** Whether *target* is a line, one of the selected line's handles, or a line's label. */
export const isOnALine = (target: EventTarget | null): boolean =>
  target instanceof Element && target.closest('.lab-line-handles, .lab-line, .lab-line-label') !== null

/** Whether *event* asks for the menu from the keyboard: the menu key, or Shift+F10. */
export const asksForTheMenu = (event: KeyboardEvent): boolean =>
  event.key === 'ContextMenu' || (event.key === 'F10' && event.shiftKey)

/** The middle of the selected line's course on screen, under *host*; null when none is drawn. */
export const selectedLineMiddle = (host: HTMLElement | null): { x: number; y: number } | null => {
  const box = host?.querySelector('.lab-line-handles__course')?.getBoundingClientRect()
  return box ? { x: box.left + box.width / 2, y: box.top + box.height / 2 } : null
}

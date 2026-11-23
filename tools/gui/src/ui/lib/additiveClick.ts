/**
 * Whether a press adds to a selection rather than replacing it: the scratchpad's notes and the diagram
 * canvas read it the same way.
 *
 * `Ctrl+click` is the context-menu gesture on Apple platforms, so accepting it as "add to the
 * selection" there would toggle an item *and* open the menu on the same click. Cmd takes its place;
 * Shift works everywhere and is what every canvas tool already trains.
 */
const APPLE = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)

export function isAdditive(event: { shiftKey: boolean; ctrlKey: boolean; metaKey: boolean }): boolean {
  return event.shiftKey || (APPLE ? event.metaKey : event.ctrlKey || event.metaKey)
}

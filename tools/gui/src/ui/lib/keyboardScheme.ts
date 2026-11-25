/**
 * Which keyboard layout the keys are named for (sketch 02·7). Letters are read by the character they
 * type (`event.key`), never by the key's position, so E, R, F and Ctrl+Z are where the keycap says on
 * any layout; the scheme decides only the one key that sits differently — `=` zooms in on QWERTY,
 * where `+` is Shift+`=`, and is not bound on QWERTZ, where `=` is Shift+`0` — and how keys are named.
 *
 * The reader chooses QWERTZ or QWERTY, or leaves it to be detected with the Keyboard Map API; where the
 * browser has none, or refuses, QWERTY is assumed and the reader is told so.
 */
export type KeyScheme = 'qwerty' | 'qwertz'
export type KeySchemeChoice = 'detect' | KeyScheme

export const KEY_SCHEME_CHOICES: readonly KeySchemeChoice[] = ['detect', 'qwertz', 'qwerty']

/** A layout as detected, and in words how it was found. */
export interface DetectedScheme {
  readonly scheme: KeyScheme
  readonly how: string
}

interface KeyboardWithLayoutMap {
  readonly getLayoutMap: () => Promise<ReadonlyMap<string, string>>
}

const layoutMapOf = (from: unknown): KeyboardWithLayoutMap | null => {
  const keyboard = (from as { keyboard?: Partial<KeyboardWithLayoutMap> } | undefined)?.keyboard
  return typeof keyboard?.getLayoutMap === 'function' ? keyboard as KeyboardWithLayoutMap : null
}

/** The layout this browser's keyboard has: the key right of T types “z” on QWERTZ. */
export const detectKeyScheme = async (from: unknown = globalThis.navigator): Promise<DetectedScheme> => {
  const keyboard = layoutMapOf(from)
  if (!keyboard) return { scheme: 'qwerty', how: 'this browser cannot tell the layout — QWERTY assumed' }
  try {
    const map = await keyboard.getLayoutMap()
    return map.get('KeyY') === 'z'
      ? { scheme: 'qwertz', how: 'the key right of T types “z”' }
      : { scheme: 'qwerty', how: 'the key right of T types “y”' }
  } catch {
    return { scheme: 'qwerty', how: 'the browser refused to tell the layout — QWERTY assumed' }
  }
}

/** What a key asks of a diagram's window: fit it, zoom in, zoom out. */
export type ViewportKey = 'fit' | 'in' | 'out'

/** The window command *event* asks for under *scheme*, or null; never with a modifier but Shift. */
export const viewportKeyOf = (
  event: Pick<KeyboardEvent, 'key' | 'ctrlKey' | 'metaKey' | 'altKey'>, scheme: KeyScheme,
): ViewportKey | null => {
  if (event.ctrlKey || event.metaKey || event.altKey) return null
  if (event.key === '0') return 'fit'
  if (event.key === '+' || (event.key === '=' && scheme === 'qwerty')) return 'in'
  return event.key === '-' || event.key === '−' ? 'out' : null
}

/** How the zoom-in key is named under *scheme*. */
export const zoomInKeyName = (scheme: KeyScheme): string => (scheme === 'qwerty' ? '+ or =' : '+')

/** Whether a key pressed on *target* is typed into a field, rather than meant for the window or the canvas. */
export const isTypingIn = (target: EventTarget | null): boolean =>
  target instanceof HTMLElement
  && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))

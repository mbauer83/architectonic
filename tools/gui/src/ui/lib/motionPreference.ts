/**
 * Whether a surface may animate right now.
 *
 * Two things say no. A missing frame clock — a test runner, a headless render, anything that is not a
 * browser paint loop — and a reader who has asked for less motion (`prefers-reduced-motion: reduce`).
 * Both get the same answer for the same reason: the resting arrangement is the contract and the
 * motion is presentation, so a surface that may not animate lands on the result at once.
 *
 * One reading, so every animation on every surface honours the preference the same way — the graph
 * layouts here, and anything that animates later.
 */
export const motionAllowed = (): boolean =>
  typeof requestAnimationFrame === 'function' && !readerPrefersReducedMotion()

const REDUCED = '(prefers-reduced-motion: reduce)'

const reducedMotionQuery = (): MediaQueryList | null =>
  typeof window !== 'undefined' && typeof window.matchMedia === 'function' ? window.matchMedia(REDUCED) : null

/** Whether the reader has asked for less motion. */
export const readerPrefersReducedMotion = (): boolean => reducedMotionQuery()?.matches ?? false

/** Call *listener* whenever the reader changes that preference; returns how to stop listening. */
export const onReducedMotionChange = (listener: (reduced: boolean) => void): (() => void) => {
  const query = reducedMotionQuery()
  const changed = (event: MediaQueryListEvent) => listener(event.matches)
  query?.addEventListener?.('change', changed)
  return () => query?.removeEventListener?.('change', changed)
}

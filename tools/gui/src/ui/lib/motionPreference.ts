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

const readerPrefersReducedMotion = (): boolean =>
  typeof window !== 'undefined'
  && typeof window.matchMedia === 'function'
  && window.matchMedia('(prefers-reduced-motion: reduce)').matches

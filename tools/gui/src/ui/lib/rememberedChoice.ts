/**
 * One of a few named choices, remembered per browser: the reader's, kept where the page can read it
 * back next time. Storage can be refused (a private window, blocked site data); the choice then holds
 * for this page only, and reads back as never made. A stored value that is not one of the choices —
 * an older spelling, a hand edit — reads back as never made too.
 */

/** The choice stored under *key* where it is one of *choices*; null where none is. */
export const rememberedChoice = <Choice extends string>(
  key: string, choices: readonly Choice[],
): Choice | null => {
  try {
    const stored = localStorage.getItem(key)
    return choices.find((choice) => choice === stored) ?? null
  } catch { return null }
}

/** Store *choice* under *key*. */
export const rememberChoice = (key: string, choice: string): void => {
  try { localStorage.setItem(key, choice) } catch { /* refused: remembered for this page only */ }
}

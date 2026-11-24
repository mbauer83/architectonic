/**
 * An on/off choice remembered per browser: the reader's, kept where the page can read it back next
 * time. Storage can be refused (a private window, blocked site data); the choice then holds for this
 * page only, and reads back as never made.
 */

/** The choice stored under *key*, or null where none is. */
export const rememberedFlag = (key: string): boolean | null => {
  try {
    const value = localStorage.getItem(key)
    return value === null ? null : value === '1'
  } catch { return null }
}

/** Store the choice under *key*. */
export const rememberFlag = (key: string, on: boolean): void => {
  try { localStorage.setItem(key, on ? '1' : '0') } catch { /* refused: remembered for this page only */ }
}

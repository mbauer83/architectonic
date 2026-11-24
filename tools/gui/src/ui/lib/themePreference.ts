/**
 * Which theme the interface wears: the system setting, or the reader's explicit choice.
 *
 * The choice is per browser, like every other preference, and is written as `data-theme` on the root
 * element, which is what `styles/tokens.css` keys its dark values on. "System" removes the attribute,
 * so the stylesheet's `prefers-color-scheme` reading applies; "light" and "dark" win over it both ways.
 *
 * Storage can refuse — a private window, blocked site data — and then the choice holds for this page
 * only. The diagram paper is not the theme's: it stays light whatever is chosen here.
 */
export type ThemeChoice = 'system' | 'light' | 'dark'

export const THEME_CHOICES: readonly ThemeChoice[] = ['system', 'light', 'dark']

export const THEME_STORAGE_KEY = 'arch.preferences.theme'

const isChoice = (value: unknown): value is ThemeChoice =>
  typeof value === 'string' && (THEME_CHOICES as readonly string[]).includes(value)

/** The remembered choice, or "system" when none is remembered or storage cannot be read. */
export const readThemeChoice = (): ThemeChoice => {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY)
    return isChoice(stored) ? stored : 'system'
  } catch {
    return 'system'
  }
}

/** Put *choice* on *root*: an explicit theme as `data-theme`, "system" as no attribute at all. */
export const applyThemeChoice = (choice: ThemeChoice, root: HTMLElement = document.documentElement): void => {
  if (choice === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', choice)
}

/** Apply *choice* and remember it for this browser. */
export const chooseTheme = (choice: ThemeChoice, root: HTMLElement = document.documentElement): void => {
  applyThemeChoice(choice, root)
  try {
    if (choice === 'system') localStorage.removeItem(THEME_STORAGE_KEY)
    else localStorage.setItem(THEME_STORAGE_KEY, choice)
  } catch { /* storage refused: the choice holds for this page only */ }
}

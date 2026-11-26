/**
 * The preferences an author sets once, per browser (sketch 01·5, 02·1, 02·7; Q3, Q5): what a selection
 * rectangle selects, whether moving and resizing snap or show the guides only as hints, which keyboard
 * layout the keys are named for, and when the list of changes is shown before saving.
 *
 * One state for the page, so the Preferences panel and the canvas read the same choice: a choice made
 * in the panel holds on the canvas at once, and `R` on the canvas shows in the panel. Each is
 * remembered in this browser (`rememberedChoice`); none changes the model or any diagram.
 */
import { computed, ref, shallowRef } from 'vue'
import type { RectangleRule } from '../../domain/layout/canvasSelection'
import type { Snapping } from '../../domain/layout/canvasSnapping'
import {
  KEY_SCHEME_CHOICES, type DetectedScheme, type KeySchemeChoice, detectKeyScheme,
} from '../lib/keyboardScheme'
import { rememberChoice, rememberedChoice } from '../lib/rememberedChoice'

/** When Save shows the list of changes first: only when the model changes (default), or always (Q3). */
export type SaveListChoice = 'model' | 'always'

export const RECTANGLE_RULES: readonly RectangleRule[] = ['touches', 'encloses']
export const SNAPPING_CHOICES: readonly Snapping[] = ['snap', 'hints']
export const SAVE_LIST_CHOICES: readonly SaveListChoice[] = ['model', 'always']

/** Where each preference is kept in this browser. */
export const PREFERENCE_KEYS = {
  rectangle: 'arch.preferences.rectangle',
  snapping: 'arch.preferences.snapping',
  keys: 'arch.preferences.keys',
  saveList: 'arch.preferences.save-list',
} as const

/** One preference: its value, read back from this browser, and setting it, which remembers it. */
const preference = <Choice extends string>(key: string, choices: readonly Choice[], fallback: Choice) => {
  const value = shallowRef<Choice>(rememberedChoice(key, choices) ?? fallback)
  const set = (choice: Choice) => {
    value.value = choice
    rememberChoice(key, choice)
  }
  return { value, set }
}

/** The editing preferences, read from this browser now. */
export const editingPreferences = (detect: () => Promise<DetectedScheme> = detectKeyScheme) => {
  const rectangle = preference(PREFERENCE_KEYS.rectangle, RECTANGLE_RULES, 'touches')
  const snapping = preference(PREFERENCE_KEYS.snapping, SNAPPING_CHOICES, 'snap')
  const keys = preference<KeySchemeChoice>(PREFERENCE_KEYS.keys, KEY_SCHEME_CHOICES, 'detect')
  const saveList = preference(PREFERENCE_KEYS.saveList, SAVE_LIST_CHOICES, 'model')
  const detected = ref<DetectedScheme | null>(null)
  void detect().then((found) => { detected.value = found })

  return {
    rectangle, snapping, keys, saveList, detected,
    /** The layout the keys are named for: the one chosen, else the one detected, else QWERTY. */
    scheme: computed(() => (keys.value.value === 'detect' ? detected.value?.scheme ?? 'qwerty' : keys.value.value)),
    /** `R`: the other rectangle rule, remembered; answers the rule now in force. */
    switchRectangle: (): RectangleRule => {
      rectangle.set(rectangle.value.value === 'touches' ? 'encloses' : 'touches')
      return rectangle.value.value
    },
  }
}

export type EditingPreferences = ReturnType<typeof editingPreferences>

let shared: EditingPreferences | null = null

/** The page's editing preferences: one state, read from this browser on first use. */
export const useEditingPreferences = (): EditingPreferences => {
  shared ??= editingPreferences()
  return shared
}

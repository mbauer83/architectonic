/**
 * The Preferences panel's editing settings, in the words of sketch 01·5, 02·1 and 02·7: each a legend,
 * its choices with the default named, the choice in force, and how to make one.
 */
import type { EditingPreferences } from '../composables/useEditingPreferences'
import { zoomInKeyName } from '../lib/keyboardScheme'

export interface PreferenceOption {
  readonly value: string
  readonly label: string
  readonly hint?: string
}

export interface PreferenceGroup {
  readonly name: string
  readonly legend: string
  readonly options: readonly PreferenceOption[]
  readonly chosen: string
  readonly choose: (value: string) => void
  readonly hints: readonly string[]
}

/** *choose* for one preference, taking only a value among *options*: the radio's own value. */
const choosing = <Choice extends string>(options: readonly Choice[], set: (choice: Choice) => void) =>
  (value: string) => {
    const choice = options.find((one) => one === value)
    if (choice !== undefined) set(choice)
  }

export const preferenceGroups = (prefs: EditingPreferences): PreferenceGroup[] => {
  const detected = prefs.detected.value
  return [
    {
      name: 'rectangle', legend: 'A selection rectangle selects', chosen: prefs.rectangle.value.value,
      options: [
        { value: 'touches', label: 'every element it touches', hint: 'default' },
        { value: 'encloses', label: 'the elements it encloses' },
      ],
      choose: choosing(['touches', 'encloses'], prefs.rectangle.set),
      hints: ['Either way a box is selected only when the rectangle encloses it. R switches while editing.'],
    },
    {
      name: 'snapping', legend: 'While moving and resizing', chosen: prefs.snapping.value.value,
      options: [
        { value: 'snap', label: 'snap to a fine grid (8 px) and to alignment guides', hint: 'default' },
        {
          value: 'hints', label: 'show alignment guides only as hints',
          hint: 'nothing snaps; a guide shows what lines up',
        },
      ],
      choose: choosing(['snap', 'hints'], prefs.snapping.set),
      hints: [],
    },
    {
      name: 'keys', legend: 'Keyboard shortcuts', chosen: prefs.keys.value.value,
      options: [
        { value: 'detect', label: 'detect the layout', hint: 'default' },
        { value: 'qwertz', label: 'QWERTZ' },
        { value: 'qwerty', label: 'QWERTY' },
      ],
      choose: choosing(['detect', 'qwertz', 'qwerty'], prefs.keys.set),
      hints: [
        detected ? `Detected: ${detected.scheme.toUpperCase()} — ${detected.how}.` : 'Detecting the layout…',
        'Letters work by the character they type on any layout. The scheme decides the key that sits'
          + ` differently — zoom in is ${zoomInKeyName(prefs.scheme.value)} — and how keys are named.`,
      ],
    },
    {
      name: 'save-list', legend: 'Show the list of changes before saving', chosen: prefs.saveList.value.value,
      options: [
        {
          value: 'model', label: 'only when the model changes',
          hint: 'default — Save is one press; a rename, new relation, details or a deletion opens the list to confirm',
        },
        { value: 'always', label: 'always' },
      ],
      choose: choosing(['model', 'always'], prefs.saveList.set),
      hints: [],
    },
  ]
}

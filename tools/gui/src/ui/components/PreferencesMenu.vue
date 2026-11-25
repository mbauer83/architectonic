<script setup lang="ts">
/**
 * The reader's per-browser preferences, at the right of the navigation bar (sketch 01·5, 02·1, 02·7).
 *
 * The theme, and the four settings an author sets once for editing diagrams (`useEditingPreferences`).
 * Further per-browser preferences belong in this one panel rather than in a control of their own
 * beside whatever they affect.
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { THEME_CHOICES, chooseTheme, readThemeChoice, type ThemeChoice } from '../lib/themePreference'
import { useEditingPreferences } from '../composables/useEditingPreferences'
import { preferenceGroups } from './preferenceGroups'

const THEME_LABELS: Record<ThemeChoice, string> = { system: 'System', light: 'Light', dark: 'Dark' }

const open = ref(false)
const theme = ref<ThemeChoice>(readThemeChoice())
const root = ref<HTMLElement | null>(null)
const prefs = useEditingPreferences()
const groups = computed(() => preferenceGroups(prefs))

const select = (choice: ThemeChoice) => {
  theme.value = choice
  chooseTheme(choice)
}

const onPointerDown = (event: PointerEvent) => {
  if (root.value && !root.value.contains(event.target as Node)) open.value = false
}
const onKeyDown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') open.value = false
}
watch(open, (isOpen) => {
  if (isOpen) {
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
  } else {
    document.removeEventListener('pointerdown', onPointerDown)
    document.removeEventListener('keydown', onKeyDown)
  }
})
onBeforeUnmount(() => { open.value = false })
</script>

<template>
  <div
    ref="root"
    class="prefs"
  >
    <button
      type="button"
      class="prefs__toggle"
      :aria-expanded="open"
      aria-controls="preferences-panel"
      aria-label="Preferences"
      title="Preferences, kept in this browser"
      data-testid="preferences-toggle"
      @click="open = !open"
    >
      <span aria-hidden="true">⚙</span>
    </button>
    <div
      v-if="open"
      id="preferences-panel"
      class="prefs__panel"
      role="dialog"
      aria-label="Preferences"
      data-testid="preferences-panel"
    >
      <h2 class="prefs__title">
        Preferences
      </h2>
      <p class="prefs__note">
        Kept in this browser only. Nothing here changes the model or any diagram.
      </p>
      <fieldset class="prefs__group">
        <legend class="prefs__legend">
          Theme
        </legend>
        <label
          v-for="choice in THEME_CHOICES"
          :key="choice"
          class="prefs__option"
        >
          <input
            type="radio"
            name="theme"
            :value="choice"
            :checked="theme === choice"
            @change="select(choice)"
          >
          <span>{{ THEME_LABELS[choice] }}</span>
        </label>
        <p class="prefs__hint">
          Diagrams stay on light paper.
        </p>
      </fieldset>
      <fieldset
        v-for="group in groups"
        :key="group.name"
        class="prefs__group"
        :data-testid="`preference-${group.name}`"
      >
        <legend class="prefs__legend">
          {{ group.legend }}
        </legend>
        <label
          v-for="option in group.options"
          :key="option.value"
          class="prefs__option"
        >
          <input
            type="radio"
            :name="`pref-${group.name}`"
            :value="option.value"
            :checked="group.chosen === option.value"
            @change="group.choose(option.value)"
          >
          <span>{{ option.label }}<small v-if="option.hint">{{ option.hint }}</small></span>
        </label>
        <p
          v-for="hint in group.hints"
          :key="hint"
          class="prefs__hint"
        >
          {{ hint }}
        </p>
      </fieldset>
    </div>
  </div>
</template>

<style scoped>
.prefs { position: relative; flex-shrink: 0; }
.prefs__toggle {
  display: flex; align-items: center; gap: 5px; padding: 4px 8px; border: none; border-radius: 4px;
  background: transparent; color: var(--nav-link); font-size: 13px; cursor: pointer; white-space: nowrap;
}
.prefs__toggle:hover, .prefs__toggle[aria-expanded="true"] { background: var(--nav-hover); color: var(--nav-text); }
.prefs__panel {
  position: absolute; top: calc(100% + 6px); right: 0; z-index: 100; width: min(340px, calc(100vw - 16px));
  max-height: calc(100vh - 80px); overflow-y: auto; padding: 10px 12px;
  background: var(--surface); color: var(--text); border: 1px solid var(--border-strong); border-radius: 8px;
  box-shadow: var(--shadow); font-size: 13px;
}
.prefs__title { margin: 0 0 2px; font-size: 14px; font-weight: 600; }
.prefs__group { border: none; display: flex; flex-direction: column; gap: 4px; margin-top: 10px; }
.prefs__legend {
  margin-bottom: 4px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em;
  color: var(--muted);
}
.prefs__option { display: flex; align-items: flex-start; gap: 6px; cursor: pointer; }
.prefs__option input { accent-color: var(--accent); margin-top: 3px; }
.prefs__option small { display: block; font-size: 11px; color: var(--muted); }
.prefs__note, .prefs__hint { font-size: 11px; color: var(--muted); }
</style>

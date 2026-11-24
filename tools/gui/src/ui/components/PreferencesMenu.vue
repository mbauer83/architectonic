<script setup lang="ts">
/**
 * The reader's per-browser preferences, at the right of the navigation bar.
 *
 * It holds the theme today. Further per-browser preferences belong in this one panel rather than in
 * a control of their own beside whatever they affect.
 */
import { onBeforeUnmount, ref, watch } from 'vue'
import { THEME_CHOICES, chooseTheme, readThemeChoice, type ThemeChoice } from '../lib/themePreference'

const LABELS: Record<ThemeChoice, string> = { system: 'System', light: 'Light', dark: 'Dark' }

const open = ref(false)
const theme = ref<ThemeChoice>(readThemeChoice())
const root = ref<HTMLElement | null>(null)

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
      title="Preferences, kept in this browser"
      @click="open = !open"
    >
      <span aria-hidden="true">⚙</span>
      <span class="prefs__label">Preferences</span>
    </button>
    <div
      v-if="open"
      id="preferences-panel"
      class="prefs__panel"
      role="dialog"
      aria-label="Preferences"
    >
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
          {{ LABELS[choice] }}
        </label>
      </fieldset>
      <p class="prefs__note">
        Kept in this browser. Diagrams stay on light paper.
      </p>
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
  position: absolute; top: calc(100% + 6px); right: 0; z-index: 100; width: 220px; padding: 10px 12px;
  background: var(--surface); color: var(--text); border: 1px solid var(--border-strong); border-radius: 8px;
  box-shadow: var(--shadow); font-size: 13px;
}
.prefs__group { border: none; display: flex; flex-direction: column; gap: 4px; }
.prefs__legend {
  margin-bottom: 4px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em;
  color: var(--muted);
}
.prefs__option { display: flex; align-items: center; gap: 6px; cursor: pointer; }
.prefs__option input { accent-color: var(--accent); }
.prefs__note { margin-top: 8px; font-size: 11px; color: var(--muted); }
@media (max-width: 1060px) { .prefs__label { display: none; } }
</style>

<script setup lang="ts">
/**
 * The primary navigation's Plan menu: the work done before the model changes, from a loose sketch
 * (scratchpads) to alternative changes (candidate architectures) to testing one against its
 * environment (stress analyses).
 *
 * Each entry is a kind of artifact a reader can hold, like every other primary entry; workflow state
 * such as proposed changes stays in the Changes menu of the status cluster.
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { candidateListRoute, scratchpadListRoute } from '../router/artifactRoutes'
import { documentsOfTypeRoute, STRESS_ANALYSIS_DOC_TYPE } from '../lib/documentListLinks'

const route = useRoute()
const open = ref(false)
const root = ref<HTMLElement | null>(null)

const ENTRIES = [
  { label: 'Scratchpads', to: scratchpadListRoute(), title: 'Notes and links on a canvas, before they are modelled' },
  { label: 'Candidate architectures', to: candidateListRoute(),
    title: 'Alternative changes to the model, sketched and compared before one is applied' },
  { label: 'Stress analyses', to: documentsOfTypeRoute(STRESS_ANALYSIS_DOC_TYPE),
    title: 'An architecture tested against the stressors of its environment' },
] as const

/** The menu is the current section while a reader is on any of its pages. */
const current = computed(() =>
  route.path.startsWith(scratchpadListRoute()) || route.path.startsWith(candidateListRoute())
  || route.path.endsWith('/workspace') || route.query.doc_type === STRESS_ANALYSIS_DOC_TYPE)

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
watch(() => route.fullPath, () => { open.value = false })
onBeforeUnmount(() => { open.value = false })
</script>

<template>
  <div
    ref="root"
    class="plan"
  >
    <button
      type="button"
      class="plan__toggle"
      :class="{ 'plan__toggle--current': current }"
      aria-haspopup="menu"
      :aria-expanded="open"
      @click="open = !open"
    >
      Plan ▾
    </button>
    <div
      v-if="open"
      class="plan__menu"
      role="menu"
      aria-label="Plan"
    >
      <RouterLink
        v-for="entry in ENTRIES"
        :key="entry.label"
        class="plan__item"
        role="menuitem"
        :to="entry.to"
        :title="entry.title"
      >
        {{ entry.label }}
      </RouterLink>
    </div>
  </div>
</template>

<style scoped>
.plan { position: relative; flex-shrink: 0; }
.plan__toggle {
  font: inherit; font-size: 13px; line-height: inherit; color: var(--nav-link); padding: 4px 8px;
  border: none; border-radius: 4px; background: transparent; cursor: pointer; white-space: nowrap;
}
.plan__toggle:hover, .plan__toggle[aria-expanded="true"] { color: var(--nav-text); background: var(--nav-hover); }
.plan__toggle--current { color: var(--nav-text); font-weight: 500; background: var(--nav-active); }
.plan__menu {
  position: absolute; top: calc(100% + 6px); left: 0; z-index: 100; min-width: 220px; padding: 4px;
  display: flex; flex-direction: column; background: var(--surface); border: 1px solid var(--border-strong);
  border-radius: 8px; box-shadow: var(--shadow);
}
.plan__item { padding: 6px 10px; border-radius: 4px; color: var(--text); font-size: 13px; white-space: nowrap; }
.plan__item:hover, .plan__item:focus-visible { background: var(--hover); text-decoration: none; }
</style>

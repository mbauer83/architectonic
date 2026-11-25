<script setup lang="ts">
/**
 * The perspectives line under a stressor input: one muted row of frameworks, each opening its
 * perspectives with a guiding question on hover or focus. *Random perspective* highlights one.
 * Choosing a perspective may put its kind on the next stressor; nothing else is recorded. Where kinds
 * are in use, a perspective no stressor is written from yet is marked, quietly.
 */
import { computed, ref } from 'vue'
import type { PerspectiveFramework, StressPerspective } from '../../../domain/schemas/stressEvaluation'
import { randomPerspective } from '../../../domain/stressAnalysis/perspectives'

const props = defineProps<{
  frameworks: readonly PerspectiveFramework[]
  /** Perspectives no stressor is written from yet, by id; empty while no stressor names a kind. */
  unwritten: ReadonlySet<string>
  /** The perspective whose kind the next stressor takes, if any. */
  chosen: string | null
}>()
const emit = defineEmits<{ choose: [perspective: StressPerspective | null] }>()

const open = ref<string | null>(null)
const highlighted = ref<string | null>(null)
/** The perspective whose question shows: the one hovered or focused, else the highlighted one. */
const asking = ref<StressPerspective | null>(null)
const shown = computed(() => props.frameworks.find((one) => one.id === open.value) ?? null)
const question = computed(() => asking.value
  ?? shown.value?.perspectives.find((one) => one.id === (highlighted.value ?? props.chosen)) ?? null)

const toggle = (id: string) => {
  open.value = open.value === id ? null : id
  highlighted.value = null
}
const random = () => {
  const drawn = randomPerspective(props.frameworks, Math.random())
  if (!drawn) return
  open.value = drawn.framework
  highlighted.value = drawn.perspective.id
}
const choose = (perspective: StressPerspective) =>
  emit('choose', props.chosen === perspective.id ? null : perspective)
</script>

<template>
  <div
    v-if="frameworks.length"
    class="perspectives"
    data-testid="perspectives"
  >
    <div class="row">
      <span class="lead">Perspectives</span>
      <template
        v-for="(framework, index) in frameworks"
        :key="framework.id"
      >
        <span
          v-if="index"
          class="sep"
          aria-hidden="true"
        >·</span>
        <button
          type="button"
          class="fw"
          :aria-expanded="open === framework.id"
          @click="toggle(framework.id)"
        >
          {{ framework.name }}
        </button>
      </template>
      <span
        class="sep"
        aria-hidden="true"
      >·</span>
      <button
        type="button"
        class="fw"
        data-testid="random-perspective"
        @click="random"
      >
        Random perspective
      </button>
    </div>
    <div
      v-if="shown"
      class="row list"
      :aria-label="shown.name"
    >
      <button
        v-for="perspective in shown.perspectives"
        :key="perspective.id"
        type="button"
        class="pv"
        :class="{ lit: highlighted === perspective.id, unwritten: unwritten.has(perspective.id) }"
        :aria-pressed="chosen === perspective.id"
        :title="perspective.question"
        :data-perspective="perspective.id"
        @mouseenter="asking = perspective"
        @mouseleave="asking = null"
        @focus="asking = perspective"
        @blur="asking = null"
        @click="choose(perspective)"
      >
        {{ perspective.name }}<span
          v-if="unwritten.has(perspective.id)"
          class="mark"
          title="No stressor from this perspective yet"
        > ◦</span>
      </button>
    </div>
    <p
      v-if="shown && question"
      class="question"
      aria-live="polite"
    >
      {{ question.question }}
    </p>
  </div>
</template>

<style scoped>
.perspectives { font-size: 11.5px; color: var(--muted); padding: 2px 10px 6px; }
.row { display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 6px; }
.lead { color: var(--faint); margin-right: 2px; }
.sep { color: var(--faint); }
.fw, .pv {
  border: none; background: none; padding: 0; font: inherit; color: var(--muted); cursor: pointer;
}
.fw:hover, .fw:focus-visible, .pv:hover, .pv:focus-visible { color: var(--accent-strong); text-decoration: underline; }
.fw[aria-expanded="true"] { color: var(--text-2); }
.list { margin-top: 3px; padding-left: 8px; border-left: 2px solid var(--border); gap: 2px 10px; }
.pv.lit { color: var(--accent-strong); font-weight: 600; }
.pv[aria-pressed="true"] { color: var(--accent-strong); text-decoration: underline; }
.mark { color: var(--faint); }
.question { margin: 3px 0 0 10px; font-style: italic; color: var(--text-2); }
</style>

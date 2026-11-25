<script setup lang="ts">
/**
 * The Reading panel (B97): what a selection on the diagram reaches, and what the picture leaves out.
 *
 * Two reach controls, **Incoming** and **Outgoing**, each none · 1 step · 2 steps · all. The flow toggle
 * latches: on stays on across selections until it is pressed again; under reduced motion it is
 * unavailable and says why. Then three lists, split honestly: *drawn here* lights the picture as well;
 * *in the model, not drawn here* and *derived* are lists only, because a picture cannot show what it
 * does not draw. Hovering or focusing a row outlines its end on the diagram.
 *
 * Presentation only: the reading itself is `useDiagramReader`'s, and every row is handed in.
 */
import { computed } from 'vue'
import type { Reach, ReachSteps } from '../../domain/diagramReading'
import { REACH_STEPS } from '../../domain/diagramReading'
import type { DerivedRow, NotDrawnRow, ReachedRow } from '../../domain/diagramReadingLists'
import { getDomainColor } from '../lib/domains'
import { toGlyphKey } from '../lib/glyphKey'
import { connectionTypeLabel } from '../../domain/connectionTypeLabel'
import ArchimateTypeGlyph from './ArchimateTypeGlyph.vue'

const props = defineProps<{
  title: string
  reach: Reach
  flowOn: boolean
  reducedMotion: boolean
  drawn: { readonly incoming: readonly ReachedRow[]; readonly outgoing: readonly ReachedRow[] }
  notDrawn: readonly NotDrawnRow[]
  derived: {
    readonly certain: readonly DerivedRow[]
    readonly potential: readonly DerivedRow[]
    loading: boolean
    failed: boolean
  }
}>()
const emit = defineEmits<{
  'update:reach': [reach: Reach]
  'toggle-flow': []
  frame: []
  'copy-link': []
  clear: []
  select: [id: string]
  hover: [id: string | null]
  /** The elements a row is about that the picture draws, outlined while it is hovered or focused. */
  point: [ids: readonly string[]]
}>()

/** The ends of a not-drawn relation that the picture draws: the selected one, and the other where drawn. */
const endsDrawn = (row: NotDrawnRow): readonly string[] => (row.otherDrawn ? [row.here, row.other] : [row.here])
const WAY_WORD = { incoming: 'incoming', outgoing: 'outgoing', undirected: 'either way' } as const
const FLOW_TITLE = 'Animate the direction of flow along the reading; stays on until switched off'
const STEP_LABEL: Record<string, string> = { 0: 'none', 1: '1 step', 2: '2 steps', all: 'all' }
const setReach = (way: keyof Reach, steps: ReachSteps) => emit('update:reach', { ...props.reach, [way]: steps })
const WAYS = [['incoming', 'Incoming'], ['outgoing', 'Outgoing']] as const
const derivedCount = computed(() => (props.derived.loading ? '…'
  : `${props.derived.certain.length} certain · ${props.derived.potential.length} potential`))
const derivedGroups = computed(() =>
  [['certain', props.derived.certain], ['potential', props.derived.potential]] as const)
/** The not-drawn rows under the reach's own headings; a relation without direction is neither. */
const NOT_DRAWN_WAYS = [['incoming', 'Incoming'], ['outgoing', 'Outgoing'], ['undirected', 'Either way']] as const
const notDrawnGroups = computed(() => NOT_DRAWN_WAYS
  .map(([way, label]) => ({ way, label, rows: props.notDrawn.filter((row) => row.way === way) }))
  .filter((group) => group.rows.length > 0))
</script>

<template>
  <section
    class="reader"
    aria-label="Reading"
    data-testid="diagram-reader"
  >
    <div class="sb-hdr">
      <span class="sb-title">Reading</span>
      <button
        type="button"
        class="det-close"
        aria-label="Clear the reading"
        title="Clear (Esc)"
        @click="emit('clear')"
      >
        ×
      </button>
    </div>
    <p
      class="subject"
      data-testid="reader-subject"
    >
      {{ title }}
    </p>

    <div
      v-for="[way, label] in WAYS"
      :key="way"
      class="row"
    >
      <span class="lbl">{{ label }}</span>
      <span
        class="seg"
        role="group"
        :aria-label="`${label} reach`"
      >
        <button
          v-for="steps in REACH_STEPS"
          :key="steps"
          type="button"
          :aria-pressed="reach[way] === steps"
          :data-reach="`${way}:${steps}`"
          @click="setReach(way, steps)"
        >{{ STEP_LABEL[steps] }}</button>
      </span>
    </div>
    <div class="row">
      <span class="lbl">Flow</span>
      <button
        type="button"
        class="flow-toggle"
        data-testid="reader-flow"
        :aria-pressed="flowOn && !reducedMotion"
        :aria-disabled="reducedMotion || undefined"
        :title="reducedMotion ? 'Reduced motion is on' : FLOW_TITLE"
        @click="emit('toggle-flow')"
      >
        {{ flowOn && !reducedMotion ? '■ Animating' : '▶ Animate' }}
      </button>
    </div>
    <p
      v-if="reducedMotion"
      class="note"
    >
      Off: this browser asks for reduced motion. The arrowheads carry the direction.
    </p>

    <details
      open
      data-testid="reader-drawn"
    >
      <summary>
        Drawn here <span class="cnt">{{ drawn.incoming.length }} incoming · {{ drawn.outgoing.length }} outgoing</span>
      </summary>
      <template
        v-for="[way, label] in WAYS"
        :key="way"
      >
        <p
          v-if="drawn[way].length"
          class="sub"
        >
          {{ label }}
        </p>
        <ul
          v-if="drawn[way].length"
          class="ent-list"
        >
          <li
            v-for="row in drawn[way]"
            :key="row.id"
            class="ent-item"
            tabindex="0"
            :data-reached="row.id"
            @click="emit('select', row.id)"
            @keydown.enter="emit('select', row.id)"
            @mouseenter="emit('hover', row.id)"
            @mouseleave="emit('hover', null)"
            @focus="emit('hover', row.id)"
            @blur="emit('hover', null)"
          >
            <span class="ent-glyph"><ArchimateTypeGlyph
              :type="toGlyphKey(row.type)"
              :size="13"
            /></span>
            <span
              class="ent-dot"
              :style="{ background: getDomainColor(row.domain) }"
            />
            <span class="ent-name">{{ row.name }}</span>
          </li>
        </ul>
      </template>
      <p
        v-if="!drawn.incoming.length && !drawn.outgoing.length"
        class="why"
      >
        Nothing within this reach.
      </p>
    </details>

    <details data-testid="reader-not-drawn">
      <summary>
        In the model, not drawn here
        <span class="cnt">{{ notDrawn.filter((row) => row.way === 'incoming').length }} incoming ·
          {{ notDrawn.filter((row) => row.way === 'outgoing').length }} outgoing</span>
      </summary>
      <template
        v-for="group in notDrawnGroups"
        :key="group.way"
      >
        <p class="sub">
          {{ group.label }}
        </p>
        <ul class="ent-list">
          <li
            v-for="row in group.rows"
            :key="row.id"
            class="ent-item ent-item--plain"
            tabindex="0"
            :data-testid="`reader-not-drawn-${row.id}`"
            @mouseenter="emit('point', endsDrawn(row))"
            @mouseleave="emit('point', [])"
            @focus="emit('point', endsDrawn(row))"
            @blur="emit('point', [])"
          >
            <span class="ent-name">{{ row.otherName }}</span>
            <span class="ent-sub">
              {{ connectionTypeLabel(row.type) }}{{ row.otherDrawn ? '' : ' · not on this diagram' }}
            </span>
          </li>
        </ul>
      </template>
      <p
        v-if="!notDrawn.length"
        class="why"
      >
        Every relation the model has for the selection within this reach is drawn.
      </p>
      <p class="why">
        One step only. Open an element to follow it, or add it in edit mode.
      </p>
    </details>

    <details data-testid="reader-derived">
      <summary>
        Derived <span class="cnt">{{ derivedCount }}</span>
      </summary>
      <p
        v-if="derived.failed"
        class="why"
      >
        The derivation could not be read for every selected element.
      </p>
      <template
        v-for="[kind, rows] in derivedGroups"
        :key="kind"
      >
        <p
          v-if="rows.length"
          class="sub"
        >
          <span :class="`chip certainty--${kind}`">{{ kind }}</span>
        </p>
        <ul
          v-if="rows.length"
          class="ent-list"
        >
          <li
            v-for="row in rows"
            :key="`${row.entityId}|${row.type}|${row.way}`"
            class="ent-item ent-item--plain"
          >
            <span class="ent-name">{{ row.name }}</span>
            <span class="ent-sub">
              {{ connectionTypeLabel(row.type) }}, {{ WAY_WORD[row.way] }} · {{ row.hops }} hops
            </span>
          </li>
        </ul>
      </template>
      <p
        v-if="!derived.loading && !derived.certain.length && !derived.potential.length"
        class="why"
      >
        The model derives nothing further within this reach.
      </p>
    </details>

    <div class="row actions">
      <button
        type="button"
        class="btn-plain"
        title="Fit the window to the reading (F)"
        @click="emit('frame')"
      >
        Frame the reading
      </button>
      <button
        type="button"
        class="btn-plain"
        data-testid="reader-copy-link"
        @click="emit('copy-link')"
      >
        Copy link
      </button>
    </div>
  </section>
</template>

<style scoped src="./DiagramReaderPanel.css"></style>

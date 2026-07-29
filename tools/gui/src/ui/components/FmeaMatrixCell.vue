<script setup lang="ts">
/**
 * One cell of the failure-mode matrix: an (element, guideword) pair and what it currently says.
 *
 * Its own component because a cell has a great deal to convey in very little space — which of three
 * states it is in, each visible factor with where its value came from, what to do next, and the one
 * judgement a person can enter — while the view around it is only laying out the grid.
 *
 * Every decision shown here was made by the server: whether occurrence is asked for at all, which
 * factors are visible, what the next action is. Nothing is derived locally, so the matrix a person
 * reads cannot disagree with the matrix an agent reads.
 */
import FmeaOccurrenceRecorder from './FmeaOccurrenceRecorder.vue'
import {
  awaitsOccurrence,
  basisGlyph,
  basisTooltip,
  cellClass,
  cellLabel,
  visibleFactors,
} from '../views/AssuranceFmeaView.helpers'
import type { CellView } from '../views/AssuranceFmeaView.helpers'

defineProps<{
  cell: CellView
  scale: readonly string[]
  /** True while this cell — and only this cell — has the recording form open. */
  recording: boolean
}>()

const emit = defineEmits<{ open: []; close: []; recorded: [] }>()
</script>

<template>
  <td :class="cellClass(cell)">
    <span class="cell-label">{{ cellLabel(cell) }}</span>

    <span
      v-if="cell.state === 'not-credible' && cell.dismissal.reason"
      class="cell-reason"
      :title="`Dismissed by ${cell.dismissal.by}: ${cell.dismissal.reason}`"
    >why</span>

    <span
      v-if="cell.state === 'recorded'"
      class="cell-factors"
    >
      <span
        v-for="factor in visibleFactors(cell)"
        :key="factor"
        class="cell-factor"
        :title="basisTooltip(factor, cell.factors[factor])"
      >
        {{ cell.factors[factor].value ?? '—' }}
        <span class="cell-basis">{{ basisGlyph(cell.factors[factor].basis) }}</span>
      </span>
    </span>

    <span
      v-if="cell.next_action"
      class="cell-next"
    >{{ cell.next_action }}</span>

    <button
      v-if="awaitsOccurrence(cell) && !recording"
      type="button"
      class="cell-record"
      @click="emit('open')"
    >
      Record occurrence
    </button>

    <FmeaOccurrenceRecorder
      v-if="recording"
      :cell="cell"
      :scale="scale"
      @recorded="emit('recorded')"
      @cancelled="emit('close')"
    />
  </td>
</template>

<style scoped>
/* Moved verbatim from the matrix view with the cell itself: the state colours are decisions, not
   decoration, and re-choosing them here would quietly change what a reader sees. */
td {
  border: 1px solid #e2e8f0;
  padding: 6px 8px;
  text-align: left;
  vertical-align: top;
  font-size: 12px;
}
.cell-label {
  display: block;
  font-weight: 600;
  text-transform: capitalize;
}
/* Untouched and not-credible must never be confusable: one has been looked at. */
.cell-untouched {
  background: #ffffff;
  color: #9ca3af;
  border-style: dashed;
}
.cell-not-credible {
  background: #f1f5f9;
  color: #475569;
}
/* `indeterminate` is deliberately unlike every band — an unrated row is a gap, not a quiet one. */
.cell-indeterminate {
  background: repeating-linear-gradient(45deg, #ffffff, #ffffff 6px, #eef2ff 6px, #eef2ff 12px);
  color: #3730a3;
}
.cell-high {
  background: #fee2e2;
  color: #991b1b;
}
.cell-medium {
  background: #fef3c7;
  color: #92400e;
}
.cell-low {
  background: #dcfce7;
  color: #166534;
}
.cell-factors {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}
.cell-factor {
  font-size: 11px;
}
.cell-basis {
  color: #6b7280;
}
.cell-reason {
  font-size: 11px;
  text-decoration: underline dotted;
  cursor: help;
}
.cell-next {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  font-style: italic;
}
.cell-record { margin-top: 4px; padding: 3px 7px; border: 1px solid #1d4ed8; border-radius: 4px;
  background: white; color: #1d4ed8; font: inherit; font-size: 11px; cursor: pointer; }
</style>

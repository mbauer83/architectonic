<script setup lang="ts">
/**
 * The failure-mode matrix for one analysis: candidate elements down, failure guidewords across.
 *
 * Rows arrive already assembled — cell state, effective factors with their basis, the priority
 * band, whether occurrence is even being asked for, and each row's next action all come from the
 * server, so this view renders decisions rather than making them.
 *
 * Two deliberate differences from a conventional FMEA worksheet are stated in the header rather
 * than left for a practitioner to discover: there is no risk priority number, and the detection
 * axis runs the other way. An expert who thinks the tool is wrong about those stops trusting the
 * derived values too.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import FmeaMatrixCell from './FmeaMatrixCell.vue'
import FmeaStructuralGaps from './FmeaStructuralGaps.vue'
import {
  coverageLine,
  elementHeading,
  elementRoute,
  guidewordLabel,
  isRecordingCell,
  worklistOrder,
} from '../views/AssuranceFmeaView.helpers'
import type { CellView, RowView } from '../views/AssuranceFmeaView.helpers'

const props = defineProps<{
  /** The FMEA this grid belongs to. Required: there is one matrix per FMEA analysis, and a grid
   *  with no analysis named was a drawing of every FMEA at once — with two analyses it showed both
   *  their rows in one table and read like a single ranking. The page shows an analysis picker
   *  until one is chosen rather than requesting an unscoped matrix. */
  analysisId: string
}>()

const rows = ref<RowView[]>([])
const locked = ref(false)
const loaded = ref(false)
const occurrenceScale = ref<string[]>([])
// One cell open at a time, keyed by its failure mode: the form carries the basis digest of the
// cell it was opened from, and two open at once invites filing a judgement against the other's.
// `null` means nothing is open; isRecordingCell keeps that apart from a cell that simply has no
// failure mode (also a null node_id).
const recording = ref<string | null>(null)

const ordered = computed(() => worklistOrder(rows.value))
const coverage = computed(() => coverageLine(rows.value))
const guidewords = computed(() => rows.value[0]?.cells.map((cell: CellView) => cell.guideword) ?? [])

const matrixUrl = computed(
  () => `/api/assurance/analyses/${encodeURIComponent(props.analysisId)}/matrix`)

async function load() {
  loaded.value = false
  const resp = await fetch(matrixUrl.value)
  if (resp.status === 423) {
    locked.value = true
    loaded.value = true
    return
  }
  if (resp.ok) {
    const body = await resp.json() as { rows: RowView[]; occurrence_scale: string[] }
    rows.value = body.rows
    occurrenceScale.value = body.occurrence_scale
  }
  loaded.value = true
}

async function onRecorded() {
  recording.value = null
  // Reloaded rather than patched in place: recording an occurrence can move the priority band, and
  // can stop the field being asked for at all. Both are the server's decisions.
  await load()
}

onMounted(() => { void load() })
watch(() => props.analysisId, () => { void load() })
</script>

<template>
  <section class="fmea-panel">
    <p
      v-if="locked"
      class="fmea-locked"
    >
      The assurance store is locked.
    </p>

    <template v-else-if="loaded">
      <p class="fmea-coverage">
        {{ coverage }}
      </p>

      <p
        v-if="!ordered.length"
        class="fmea-empty"
      >
        No candidate elements yet. Elements appear here once a control structure names them.
        Where the architecture graph shows an element to be load-bearing that no analysis has
        reached, verification reports it — with what relies on it — rather than adding a blank row.
      </p>

      <table
        v-else
        class="fmea-table"
      >
        <thead>
          <tr>
            <th class="fmea-element">
              Element
            </th>
            <th
              v-for="guideword in guidewords"
              :key="guideword"
            >
              {{ guidewordLabel(guideword) }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in ordered"
            :key="row.element_id"
          >
            <th class="fmea-element">
              <RouterLink
                v-if="elementRoute(row)"
                class="fmea-element-name fmea-element-link"
                :to="elementRoute(row)!"
              >
                {{ elementHeading(row).primary }}
              </RouterLink>
              <span
                v-else
                class="fmea-element-name"
              >{{ elementHeading(row).primary }}</span>
              <span
                v-if="elementHeading(row).secondary"
                class="fmea-element-id"
              >{{ elementHeading(row).secondary }}</span>
              <span class="fmea-nominated">{{ row.nominated_by.join(', ') }}</span>
            </th>
            <FmeaMatrixCell
              v-for="cell in row.cells"
              :key="cell.guideword"
              :cell="cell"
              :scale="occurrenceScale"
              :recording="isRecordingCell(recording, cell)"
              @open="recording = cell.node_id"
              @close="recording = null"
              @recorded="onRecorded"
            />
          </tr>
        </tbody>
      </table>

      <FmeaStructuralGaps />
    </template>
  </section>
</template>


<style scoped>
.fmea-panel {
  padding: 20px;
}
.fmea-title {
  font-size: 20px;
  margin: 0 0 8px;
}
.fmea-note,
.fmea-coverage,
.fmea-empty,
.fmea-locked {
  font-size: 13px;
  color: #4b5563;
  margin: 0 0 12px;
  max-width: 70ch;
}
.fmea-table {
  border-collapse: collapse;
  width: 100%;
  font-size: 12px;
}
.fmea-table th,
.fmea-table td {
  border: 1px solid #e2e8f0;
  padding: 6px 8px;
  text-align: left;
  vertical-align: top;
}
.fmea-element {
  white-space: nowrap;
}
.fmea-element-name {
  display: block;
  font-weight: 600;
}
/* Reads as the heading it is until pointed at — the row is about this element, and the link is a
   way out of the matrix rather than the point of the cell. */
.fmea-element-link {
  color: inherit;
  text-decoration: none;
}
.fmea-element-link:hover,
.fmea-element-link:focus-visible {
  color: #2563eb;
  text-decoration: underline;
}
/* The id is demoted, never dropped: it is what an analyst quotes in a review. */
.fmea-element-id {
  display: block;
  font-size: 11px;
  color: #9ca3af;
  font-family: monospace;
}
.fmea-nominated {
  display: block;
  font-size: 11px;
  color: #6b7280;
}
</style>

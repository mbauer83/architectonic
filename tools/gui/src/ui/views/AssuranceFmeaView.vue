<script setup lang="ts">
/**
 * The failure-mode matrix as a standalone page, scoped by `?analysis=`.
 *
 * A page wrapper now: the grid itself is `FmeaMatrixPanel`, because there is one matrix per FMEA
 * analysis and the derived-diagram surface has to draw the same grid. A single global matrix was the
 * defect — with two FMEAs it showed both analyses' rows in one table, and the second analysis had
 * nowhere of its own to put one.
 *
 * The two deliberate departures from a conventional FMEA worksheet are stated here rather than left
 * for a practitioner to discover: there is no risk priority number, and the detection axis runs the
 * other way. An expert who thinks the tool is wrong about those stops trusting the derived values.
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AssuranceAnalysisPicker from '../components/AssuranceAnalysisPicker.vue'
import FmeaMatrixPanel from '../components/FmeaMatrixPanel.vue'

const route = useRoute()
const router = useRouter()

const analysisId = computed(() =>
  typeof route.query['analysis'] === 'string' && route.query['analysis']
    ? route.query['analysis']
    : null)

// The picker's own selection, mirrored into the URL so the chosen matrix is linkable and a reload
// lands on the same grid. There is no unscoped matrix to fall back to.
const chosen = ref<string | null>(analysisId.value)
watch(analysisId, (value) => { chosen.value = value })
watch(chosen, (value) => {
  if (value && value !== analysisId.value) {
    // `analysis` is the page's only query parameter, so it is written rather than merged.
    void router.replace({ path: route.path, query: { analysis: value } })
  }
})
</script>

<template>
  <section class="fmea-page">
    <h1 class="fmea-title">
      FMEA Matrix
    </h1>
    <p class="fmea-note">
      Severity and detectability are derived from the model. Occurrence is asked for only where it
      could change the priority. There is no risk priority number: multiplying ordinals is not a
      quantity. Detectability runs from <strong>very-low</strong> (nothing would catch it) to
      <strong>very-high</strong> — the opposite direction to conventional FMEA detection numbers.
    </p>
    <p
      v-if="!analysisId"
      class="fmea-note fmea-note--scope"
    >
      A matrix belongs to one FMEA analysis — choose which one. There is no matrix of every failure
      mode in the store: a single ranking across two analyses is not a ranking of either.
    </p>
    <AssuranceAnalysisPicker
      v-if="!analysisId"
      v-model="chosen"
      default-method="FMEA"
    />

    <FmeaMatrixPanel
      v-if="analysisId"
      :analysis-id="analysisId"
    />
  </section>
</template>

<style scoped>
.fmea-page { padding: 20px; }
.fmea-title { font-size: 20px; margin: 0 0 8px; }
.fmea-note { font-size: 13px; color: #4b5563; margin: 0 0 12px; max-width: 70ch; }
.fmea-note--scope { color: #6b7280; }
</style>

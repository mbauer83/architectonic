<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  parseCandidates,
  parseCoverage,
  scoreBand,
  componentHasBlockingGap,
  type ScanCandidate,
  type AibomCoverage,
} from './AssuranceAibom.helpers'

const candidates = ref<ScanCandidate[]>([])
const coverage = ref<AibomCoverage | null>(null)
const exportJson = ref<string>('')
const error = ref<string | null>(null)
const busy = ref(false)

onMounted(loadCoverage)

async function loadCoverage() {
  try {
    const resp = await fetch('/api/assurance/aibom/coverage')
    if (resp.ok) coverage.value = parseCoverage(await resp.json())
  } catch { /* coverage is advisory; a load failure leaves the section empty */ }
}

async function runScan() {
  error.value = null
  busy.value = true
  try {
    const resp = await fetch('/api/assurance/aibom/scan')
    if (!resp.ok) { error.value = `HTTP ${resp.status}`; return }
    candidates.value = parseCandidates(await resp.json())
  } catch (e) {
    error.value = String(e)
  } finally {
    busy.value = false
  }
}

async function exportBom() {
  error.value = null
  busy.value = true
  exportJson.value = ''
  try {
    const resp = await fetch('/api/assurance/aibom/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes: 'Model-derived ML-BOM.' }),
    })
    if (!resp.ok) { error.value = `HTTP ${resp.status}`; return }
    const body = await resp.json() as { bom: unknown; coverage: unknown }
    exportJson.value = JSON.stringify(body.bom, null, 2)
    if (body.coverage) coverage.value = parseCoverage(body.coverage)
  } catch (e) {
    error.value = String(e)
  } finally {
    busy.value = false
  }
}

function download() {
  const blob = new Blob([exportJson.value], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'ml-bom.cdx.json'
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <section class="aibom">
    <p class="hint-note">
      An AI-BOM is DERIVED from the architecture model: every entity you mark with an AI
      specialization (ai-model, ai-agent, ai-dataset, …) becomes a component, with its model
      card and dataset/governance links read from the model. Mark candidates on their entity
      page, then export the CycloneDX 1.6 ML-BOM here.
    </p>

    <div
      v-if="error"
      class="wiz-error"
    >
      {{ error }}
    </div>

    <!-- Coverage: what is missing for a valid AIBOM -->
    <div class="block">
      <div class="row">
        <h3 class="block-title">
          Coverage
        </h3>
        <button
          class="add-btn add-btn--ghost"
          type="button"
          :disabled="busy"
          @click="loadCoverage"
        >
          Refresh
        </button>
      </div>
      <template v-if="coverage && coverage.components.length">
        <p
          v-if="coverage.unbound_roles.length"
          class="dim"
        >
          Unbound derivation roles (no connection type maps to them):
          {{ coverage.unbound_roles.join(', ') }}
        </p>
        <table class="grid">
          <thead>
            <tr>
              <th>Component</th>
              <th>Specialization</th>
              <th>Gaps</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="c in coverage.components"
              :key="c.entity_id"
            >
              <td>{{ c.name }}</td>
              <td class="dim">
                {{ c.specialization }}
              </td>
              <td>
                <span
                  v-if="!componentHasBlockingGap(c) && !c.missing_recommended_attributes.length"
                  class="badge band--high"
                >complete</span>
                <template v-else>
                  <span
                    v-if="c.missing_required_attributes.length"
                    class="badge band--low"
                  >missing required: {{ c.missing_required_attributes.join(', ') }}</span>
                  <span
                    v-if="c.missing_dataset_linkage"
                    class="badge band--low"
                  >no dataset link</span>
                  <span
                    v-if="c.missing_governance"
                    class="badge band--low"
                  >no governance</span>
                  <span
                    v-if="c.missing_recommended_attributes.length"
                    class="badge band--medium"
                  >advisory: {{ c.missing_recommended_attributes.join(', ') }}</span>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </template>
      <p
        v-else
        class="empty"
      >
        No AI components in the model yet. Mark entities with an AI specialization to populate
        the AI-BOM.
      </p>
    </div>

    <!-- Candidate scan (assistive) -->
    <div class="block">
      <div class="row">
        <h3 class="block-title">
          AI-candidate scan
        </h3>
        <button
          class="add-btn"
          type="button"
          :disabled="busy"
          @click="runScan"
        >
          Scan architecture
        </button>
      </div>
      <p class="dim">
        Heuristic suggestions only — confirm each, then mark it on its entity page (set an AI
        specialization). Marking is what puts it in the AI-BOM.
      </p>
      <table
        v-if="candidates.length"
        class="grid"
      >
        <thead>
          <tr>
            <th>Name</th>
            <th>Type</th>
            <th>Score</th>
            <th>Reasons</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="c in candidates"
            :key="c.entity_id"
          >
            <td>{{ c.name }}</td>
            <td class="dim">
              {{ c.entity_type }}
            </td>
            <td>
              <span
                class="badge"
                :class="`band--${scoreBand(c.score)}`"
              >{{ c.score }}</span>
            </td>
            <td class="dim">
              {{ c.reasons.join(', ') }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Export -->
    <div class="block">
      <div class="row">
        <h3 class="block-title">
          Export ML-BOM
        </h3>
        <button
          class="add-btn"
          type="button"
          :disabled="busy"
          @click="exportBom"
        >
          Export model-derived ML-BOM
        </button>
      </div>
      <div
        v-if="exportJson"
        class="export"
      >
        <button
          class="add-btn add-btn--ghost"
          type="button"
          @click="download"
        >
          ⭳ Download .cdx.json
        </button>
        <pre class="export-json">{{ exportJson }}</pre>
      </div>
    </div>
  </section>
</template>

<style scoped>
.aibom { display: flex; flex-direction: column; gap: 16px; }
.hint-note {
  font-size: 13px; color: #475569; background: #f8fafc;
  border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 14px; margin: 0;
}
.wiz-error { padding: 10px 14px; background: #fef2f2; color: #b91c1c; border-radius: 6px; font-size: 13px; }
.block {
  border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 14px;
  display: flex; flex-direction: column; gap: 10px;
}
.block-title { font-size: 14px; font-weight: 700; margin: 0; }
.row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.add-btn {
  font-size: 13px; padding: 7px 14px; border: none; border-radius: 6px;
  background: #2563eb; color: #fff; font-weight: 600; cursor: pointer;
}
.add-btn--ghost { background: #fff; color: #2563eb; border: 1px solid #cbd5e1; }
.add-btn:disabled { opacity: 0.5; cursor: default; }
.empty { color: #94a3b8; font-size: 13px; margin: 0; }
.dim { color: #94a3b8; font-size: 12px; }
.grid { border-collapse: collapse; font-size: 12px; width: 100%; }
.grid th, .grid td { border: 1px solid #e2e8f0; padding: 6px 10px; text-align: left; }
.grid th { background: #f8fafc; font-weight: 600; }
.badge {
  font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 600;
  margin-right: 4px; display: inline-block;
}
.band--high { background: #dcfce7; color: #15803d; }
.band--medium { background: #fef9c3; color: #854d0e; }
.band--low { background: #fee2e2; color: #b91c1c; }
.export { display: flex; flex-direction: column; gap: 8px; }
.export-json {
  background: #0f172a; color: #e2e8f0; font-size: 11px; padding: 10px 12px;
  border-radius: 6px; overflow: auto; max-height: 320px; margin: 0;
}
</style>

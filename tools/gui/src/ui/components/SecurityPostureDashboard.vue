<script setup lang="ts">
/**
 * Security posture for one architecture anchor: the metric grid
 * from the ACTIVE signal snapshot (unit-explicit, exposure-filtered) plus the
 * audited VEX assessment form. Numbers come from the same use case the MCP
 * metrics tool serializes; recording a VEX assessment re-fetches so the
 * analyst watches counts change.
 */
import { ref, watch } from 'vue'
import {
  VEX_STATUSES, stateMessage, showsMetrics, vexFormErrors,
  type SecurityMetricsPayload, type VexFormValues,
} from './SecurityPostureDashboard.helpers'

const props = defineProps<{ anchorEntityId: string }>()

const metrics = ref<SecurityMetricsPayload | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

const form = ref<VexFormValues>({
  canonical_component_id: '', canonical_vulnerability_id: '',
  vex_status: 'under_investigation', justification: '', author: '',
})
const formErrors = ref<string[]>([])
const formResult = ref<string | null>(null)
const submitting = ref(false)

async function loadMetrics() {
  if (!props.anchorEntityId) { metrics.value = null; return }
  loading.value = true
  error.value = null
  try {
    const resp = await fetch(
      `/api/assurance/security-metrics?anchor_entity_id=${encodeURIComponent(props.anchorEntityId)}`)
    if (resp.status === 423) { error.value = 'Store is locked.'; return }
    if (!resp.ok) { error.value = `HTTP ${resp.status}`; return }
    metrics.value = await resp.json() as SecurityMetricsPayload
  } catch (e) {
    error.value = String(e)
  } finally {
    loading.value = false
  }
}

watch(() => props.anchorEntityId, loadMetrics, { immediate: true })

async function submitVex() {
  formErrors.value = vexFormErrors(form.value)
  formResult.value = null
  if (formErrors.value.length > 0) return
  submitting.value = true
  try {
    const resp = await fetch('/api/assurance/vex', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ anchor_entity_id: props.anchorEntityId, ...form.value }),
    })
    const body = await resp.json().catch(() => ({})) as Record<string, unknown>
    if (!resp.ok) {
      const fallback = typeof body.message === 'string'
        ? body.message
        : typeof body.error === 'string' ? body.error : `HTTP ${resp.status}`
      const detail = Array.isArray(body.errors)
        ? (body.errors as { message: string }[]).map((e) => e.message).join('; ')
        : fallback
      formErrors.value = [detail]
      return
    }
    formResult.value = `recorded revision ${String(body.revision)}`
    await loadMetrics()
  } catch (e) {
    formErrors.value = [String(e)]
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="posture">
    <p class="posture-hint">
      Security posture from the ACTIVE signal snapshot for this anchor — the same
      numbers the MCP metrics tool reports. Suppressing VEX statuses
      (not_affected / fixed) require a justification.
    </p>
    <div
      v-if="loading"
      class="posture-note"
    >
      Loading…
    </div>
    <div
      v-else-if="error"
      class="posture-error"
    >
      {{ error }}
    </div>
    <template v-else-if="metrics">
      <div
        v-if="stateMessage(metrics)"
        class="posture-note"
      >
        {{ stateMessage(metrics) }}
      </div>
      <template v-if="showsMetrics(metrics)">
        <div class="posture-header">
          <span
            v-if="metrics.computed_classification"
            class="classification-chip"
          >{{ metrics.computed_classification }}</span>
          <span class="basis">basis snapshot <code>{{ metrics.basis_snapshot_id }}</code>
            · activated {{ metrics.basis_activated_at }}</span>
        </div>
        <dl class="metric-grid">
          <div class="metric">
            <dt>distinct open vulnerabilities</dt>
            <dd>{{ metrics.distinct_open_vulnerabilities }}</dd>
          </div>
          <div class="metric">
            <dt>component findings</dt>
            <dd>{{ metrics.finding_total }}</dd>
          </div>
          <div class="metric">
            <dt>components</dt>
            <dd>{{ metrics.component_count }}</dd>
          </div>
          <div class="metric">
            <dt>max CVSS</dt>
            <dd>{{ metrics.max_cvss_score ?? '—' }} ({{ metrics.max_severity_band ?? 'n/a' }})</dd>
          </div>
          <div class="metric">
            <dt>open findings by directness</dt>
            <dd>
              <span
                v-for="(count, directness) in metrics.open_component_findings"
                :key="directness"
                class="pair"
              >{{ directness }}: {{ count }}</span>
              <span v-if="!Object.keys(metrics.open_component_findings ?? {}).length">none</span>
            </dd>
          </div>
          <div class="metric">
            <dt>findings by severity band</dt>
            <dd>
              <span
                v-for="(count, band) in metrics.severity_band_counts"
                :key="band"
                class="pair"
              >{{ band }}: {{ count }}</span>
              <span v-if="!Object.keys(metrics.severity_band_counts ?? {}).length">none</span>
            </dd>
          </div>
          <div class="metric">
            <dt>unknown severity / applicability</dt>
            <dd>{{ metrics.unknown_severity_finding_count }} / {{ metrics.applicability_unknown_count }}</dd>
          </div>
          <div class="metric">
            <dt>suppressed by VEX</dt>
            <dd>{{ metrics.suppressed_finding_count }}</dd>
          </div>
        </dl>

        <form
          class="vex-form"
          @submit.prevent="submitVex"
        >
          <div class="vex-title">
            Record VEX assessment
          </div>
          <input
            v-model="form.canonical_component_id"
            class="vex-input"
            placeholder="component (purl incl. version, e.g. pkg:pypi/requests@2.31.0)"
          >
          <input
            v-model="form.canonical_vulnerability_id"
            class="vex-input"
            placeholder="canonical vulnerability id (VID@…)"
          >
          <div class="vex-row">
            <select
              v-model="form.vex_status"
              class="vex-input"
            >
              <option
                v-for="status in VEX_STATUSES"
                :key="status"
                :value="status"
              >
                {{ status }}
              </option>
            </select>
            <input
              v-model="form.author"
              class="vex-input"
              placeholder="author"
            >
          </div>
          <textarea
            v-model="form.justification"
            class="vex-input"
            rows="2"
            placeholder="justification (required for not_affected / fixed)"
          />
          <div
            v-for="formError in formErrors"
            :key="formError"
            class="posture-error"
          >
            {{ formError }}
          </div>
          <div
            v-if="formResult"
            class="vex-ok"
          >
            {{ formResult }}
          </div>
          <button
            type="submit"
            class="vex-submit"
            :disabled="submitting"
          >
            {{ submitting ? 'Recording…' : 'Record assessment' }}
          </button>
        </form>
      </template>
    </template>
  </div>
</template>

<style scoped>
.posture { display: flex; flex-direction: column; gap: 12px; }
.posture-hint { font-size: 12px; color: #64748b; margin: 0; }
.posture-note {
  font-size: 12px; color: #92400e; background: #fef3c7;
  border: 1px solid #f59e0b; border-radius: 6px; padding: 6px 10px;
}
.posture-error { font-size: 12px; color: #b91c1c; }
.posture-header { display: flex; align-items: center; gap: 10px; font-size: 12px; color: #475569; }
.classification-chip {
  background: #1e293b; color: #f8fafc; border-radius: 4px;
  padding: 1px 8px; font-size: 11px; font-weight: 600;
}
.basis code { font-size: 11px; }
.metric-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 8px; margin: 0;
}
.metric { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px 10px; }
.metric dt { font-size: 11px; color: #64748b; }
.metric dd { margin: 2px 0 0; font-size: 15px; font-weight: 600; color: #0f172a; }
.pair { margin-right: 8px; font-size: 13px; }
.vex-form {
  display: flex; flex-direction: column; gap: 6px;
  border-top: 1px solid #e2e8f0; padding-top: 10px;
}
.vex-title { font-size: 12px; font-weight: 600; color: #374151; }
.vex-row { display: flex; gap: 6px; }
.vex-input {
  font-size: 12px; padding: 5px 8px; border: 1px solid #d1d5db;
  border-radius: 5px; width: 100%; box-sizing: border-box;
}
.vex-ok { font-size: 12px; color: #15803d; }
.vex-submit {
  align-self: flex-start; padding: 5px 14px; font-size: 12px;
  background: #2563eb; color: white; border: none; border-radius: 5px; cursor: pointer;
}
.vex-submit:disabled { opacity: 0.5; }
</style>

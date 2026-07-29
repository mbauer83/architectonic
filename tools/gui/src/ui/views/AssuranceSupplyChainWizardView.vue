<script setup lang="ts">
import { ref, computed } from 'vue'
import EntityPickerInput from '../components/EntityPickerInput.vue'
import AssuranceAibomPanel from './AssuranceAibomPanel.vue'
import type { EntityDisplayInfo } from '../../domain'
import SignalIngestPanel from '../components/SignalIngestPanel.vue'
import {
  SUPPLY_STEPS,
  ADMISSIBLE_ANCHOR_TYPES,
  SEVERITY_ORDER,
  summariseSeverities,
  type SupplyStep,
  type BomComponent,
  type VulnRecord,
} from './AssuranceSupplyChainWizard.helpers'
import SecurityPostureDashboard from '../components/SecurityPostureDashboard.vue'

const stepKey = ref<string>('scope')
const currentStep = computed<SupplyStep>(
  () => SUPPLY_STEPS.find((s) => s.key === stepKey.value) ?? SUPPLY_STEPS[0],
)

const anchorId = ref<string>('')
const anchorName = ref<string>('')
const anchorType = ref<string>('')

const components = ref<BomComponent[]>([])
const vulns = ref<VulnRecord[]>([])
const severityFilter = ref<string>('')
const withheld = ref(0)
const error = ref<string | null>(null)

const fixedTypes = [...ADMISSIBLE_ANCHOR_TYPES]
const hasAnchor = computed(() => anchorId.value !== '')
const severityCounts = computed(() => summariseSeverities(vulns.value))
const filteredVulns = computed(() => (
  severityFilter.value
    ? vulns.value.filter((v) => (v.severity ?? 'unknown').toLowerCase() === severityFilter.value)
    : vulns.value
))

function onScopeSelect(entity: EntityDisplayInfo) {
  anchorId.value = entity.artifact_id
  anchorName.value = entity.name
  anchorType.value = entity.artifact_type
  error.value = null
}

function clearAnchor() {
  anchorId.value = ''
  anchorName.value = ''
  anchorType.value = ''
  components.value = []
}

function goToStep(key: string) {
  const step = SUPPLY_STEPS.find((s) => s.key === key)
  if (step?.needsAnchor && !hasAnchor.value) return
  stepKey.value = key
  if (key === 'components') void loadComponents()
  if (key === 'vulnerabilities') void loadVulns()
}

async function loadComponents() {
  if (!hasAnchor.value) return
  const resp = await fetch(
    `/api/assurance/security-components?anchor_entity_id=${encodeURIComponent(anchorId.value)}`)
  if (resp.status === 423) { error.value = 'Assurance signals are not available (store locked).'; return }
  if (!resp.ok) { components.value = []; return }
  const body = await resp.json() as { components: BomComponent[]; withheld?: number }
  components.value = body.components ?? []
  withheld.value = body.withheld ?? 0
}

async function loadVulns() {
  if (!hasAnchor.value) return
  const resp = await fetch(
    `/api/assurance/security-findings?anchor_entity_id=${encodeURIComponent(anchorId.value)}`)
  if (resp.status === 423) { error.value = 'Assurance signals are not available (store locked).'; return }
  if (!resp.ok) { vulns.value = []; return }
  // The findings surface names its fields for the snapshot model; map them onto the
  // table's shape rather than reshaping the endpoint for one view.
  const body = await resp.json() as {
    findings: {
      canonical_vulnerability_id: string
      severity_band?: string | null
      component_purl?: string | null
      component_name?: string | null
      provenance?: string | null
    }[]
    withheld?: number
  }
  vulns.value = (body.findings ?? []).map((f) => {
    let osvId: string | undefined
    try {
      const provenance = f.provenance ? JSON.parse(f.provenance) as Record<string, string> : {}
      osvId = provenance['osv_id']
    } catch { osvId = undefined }
    return {
      vuln_id: osvId ?? f.canonical_vulnerability_id,
      id: f.canonical_vulnerability_id,
      severity: f.severity_band ?? 'unknown',
      purl: f.component_purl ?? '',
      summary: f.component_name ?? '',
    }
  })
  withheld.value = body.withheld ?? 0
}

</script>

<template>
  <div class="wiz">
    <div class="wiz-header">
      <h1 class="wiz-title">
        Supply-chain wizard
      </h1>
      <p class="wiz-sub">
        Ingest an SBOM for an architecture element and read back the resulting
        signal snapshot: components, vulnerabilities, posture and VEX. The same
        ingest is available directly from the element's own detail page.
      </p>
    </div>

    <div
      v-if="error"
      class="wiz-error"
    >
      {{ error }}
    </div>

    <!-- Stepper -->
    <nav class="stepper">
      <button
        v-for="(s, i) in SUPPLY_STEPS"
        :key="s.key"
        class="step-tab"
        :class="{
          'step-tab--active': s.key === stepKey,
          'step-tab--locked': s.needsAnchor && !hasAnchor,
        }"
        type="button"
        :disabled="s.needsAnchor && !hasAnchor"
        @click="goToStep(s.key)"
      >
        <span class="step-num">{{ i + 1 }}</span>
        {{ s.label }}
        <span
          v-if="s.needsAnchor && !hasAnchor"
          class="lock"
        >🔒</span>
      </button>
    </nav>

    <!-- Scope -->
    <section
      v-if="currentStep.key === 'scope'"
      class="step-body"
    >
      <p class="hint-note">
        Choose the architecture element this SBOM describes. Scope is expressed in
        ArchiMate terms — a single application-component (one service), an
        application-collaboration or grouping (a system or subset), or a technology
        node / system-software. Components and vulnerabilities bind under this scope.
      </p>
      <div
        v-if="hasAnchor"
        class="anchor-chip"
      >
        <span class="anchor-name">{{ anchorName }}</span>
        <span class="anchor-type">{{ anchorType }}</span>
        <button
          class="anchor-clear"
          type="button"
          @click="clearAnchor"
        >
          change
        </button>
      </div>
      <EntityPickerInput
        v-else
        :fixed-entity-types="fixedTypes"
        widenable-to="none"
        placeholder="Search architecture elements for the SBOM scope…"
        @select="onScopeSelect"
      />
      <p
        v-if="hasAnchor"
        class="ok-note"
      >
        Scope set. Continue to <strong>Ingest SBOM</strong>.
      </p>
    </section>

    <!-- Ingest SBOM — the same component the entity page uses, so the two
         surfaces cannot drift in what they accept or how they report it. -->
    <section
      v-else-if="currentStep.key === 'ingest'"
      class="step-body"
    >
      <p class="scope-line">
        Scope: <strong>{{ anchorName }}</strong> <span class="anchor-type">{{ anchorType }}</span>
      </p>
      <SignalIngestPanel
        :artifact-id="anchorId"
        :entity-type="anchorType"
        @ingested="() => { void loadComponents(); void loadVulns() }"
      />
    </section>

    <!-- Components -->
    <section
      v-else-if="currentStep.key === 'components'"
      class="step-body"
    >
      <div class="row">
        <p class="scope-line">
          Scope: <strong>{{ anchorName }}</strong>
        </p>
        <button
          class="add-btn add-btn--ghost"
          type="button"
          @click="loadComponents"
        >
          ↺ Reload
        </button>
        <span class="match-summary">
          {{ components.length }} component{{ components.length === 1 ? '' : 's' }}
        </span>
      </div>
      <p
        v-if="withheld > 0"
        class="hint-note"
      >
        {{ withheld }} record(s) above your classification ceiling are not shown.
      </p>
      <p
        v-if="components.length === 0"
        class="empty"
      >
        No active signal snapshot for this scope yet — use the
        <strong>Ingest SBOM</strong> step, or run an ingest from the CLI
        (<code>arch-assurance seed --with-signals</code>, the ingest script) or the
        MCP/REST surface.
      </p>
      <table
        v-else
        class="grid"
      >
        <thead>
          <tr>
            <th>Component</th>
            <th>Version</th>
            <th>Directness</th>
            <th>purl</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="c in components"
            :key="c.component_id ?? c.purl ?? c.name"
          >
            <td>{{ c.name }}</td>
            <td>{{ c.version }}</td>
            <td>{{ c.directness ?? 'unknown' }}</td>
            <td><code>{{ c.purl }}</code></td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- Vulnerabilities -->
    <section
      v-else-if="currentStep.key === 'vulnerabilities'"
      class="step-body"
    >
      <div class="row">
        <p class="scope-line">
          Scope: <strong>{{ anchorName }}</strong>
        </p>
        <select
          v-model="severityFilter"
          class="sev-select"
          aria-label="Severity filter"
          @change="() => {}"
        >
          <option value="">
            all severities
          </option>
          <option
            v-for="sev in SEVERITY_ORDER"
            :key="sev"
            :value="sev"
          >
            {{ sev }}
          </option>
        </select>
        <button
          class="add-btn add-btn--ghost"
          type="button"
          @click="loadVulns"
        >
          ↺ Reload
        </button>
      </div>
      <div
        v-if="severityCounts.length"
        class="sev-bar"
      >
        <span
          v-for="s in severityCounts"
          :key="s.severity"
          class="sev-pill"
          :class="`sev-pill--${s.severity}`"
        >{{ s.severity }}: {{ s.count }}</span>
      </div>
      <p
        v-if="filteredVulns.length === 0"
        class="empty"
      >
        No vulnerability findings in the active snapshot for the current filter.
      </p>
      <table
        v-else
        class="grid"
      >
        <thead>
          <tr>
            <th>Id</th>
            <th>Severity</th>
            <th>purl</th>
            <th>Summary</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(v, idx) in filteredVulns"
            :key="v.vuln_id ?? v.id ?? idx"
          >
            <td class="mono">
              {{ v.vuln_id ?? v.id }}
            </td>
            <td>
              <span
                class="badge"
                :class="`sev-pill--${(v.severity ?? 'unknown').toLowerCase()}`"
              >{{ v.severity ?? 'unknown' }}</span>
            </td>
            <td class="mono">
              {{ v.purl }}
            </td>
            <td>{{ v.summary }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- Posture & VEX -->
    <section
      v-else-if="currentStep.key === 'posture'"
      class="step-body"
    >
      <SecurityPostureDashboard :anchor-entity-id="anchorId" />
    </section>

    <!-- AI-BOM -->
    <section
      v-else
      class="step-body"
    >
      <AssuranceAibomPanel />
    </section>
  </div>
</template>

<style scoped>
.wiz { padding: 20px 24px; max-width: 960px; }
.wiz-header { margin-bottom: 16px; }
.wiz-title { font-size: 20px; font-weight: 700; margin: 0 0 4px; }
.wiz-sub { color: #64748b; font-size: 13px; margin: 0; }
.wiz-error { padding: 10px 14px; background: #fef2f2; color: #b91c1c; border-radius: 6px; margin-bottom: 12px; font-size: 13px; }
.stepper { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; }
.step-tab {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 12px; border: 1px solid #e2e8f0; border-radius: 6px;
  background: #fff; color: #475569; font-size: 13px; cursor: pointer;
}
.step-tab--active { background: #2563eb; color: #fff; border-color: #2563eb; }
.step-tab--locked { opacity: 0.55; cursor: not-allowed; }
.step-num {
  display: inline-flex; align-items: center; justify-content: center;
  width: 18px; height: 18px; border-radius: 50%; background: #e2e8f0; color: #475569; font-size: 11px;
}
.step-tab--active .step-num { background: rgba(255,255,255,0.3); color: #fff; }
.lock { font-size: 11px; }
.step-body { display: flex; flex-direction: column; gap: 12px; }
.hint-note { font-size: 13px; color: #475569; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 14px; margin: 0; }
.anchor-chip { display: flex; align-items: center; gap: 10px; padding: 10px 14px; border: 1px solid #86efac; background: #f0fdf4; border-radius: 8px; }
.anchor-name { font-weight: 600; font-size: 14px; }
.anchor-type { font-size: 11px; color: #64748b; background: #e2e8f0; padding: 2px 8px; border-radius: 10px; }
.anchor-clear { font-size: 12px; color: #2563eb; background: none; border: none; cursor: pointer; }
.scope-line { font-size: 13px; color: #475569; margin: 0; }
.ok-note { font-size: 13px; color: #15803d; margin: 0; }
.row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.json-input { width: 100%; font-family: ui-monospace, monospace; font-size: 12px; padding: 8px 10px; border: 1px solid #cbd5e1; border-radius: 6px; }
.add-btn {
  font-size: 13px; padding: 7px 14px; border: none; border-radius: 6px;
  background: #2563eb; color: #fff; font-weight: 600; cursor: pointer;
}
.add-btn--ghost { background: #fff; color: #2563eb; border: 1px solid #cbd5e1; }
.add-btn:disabled { opacity: 0.5; cursor: default; }
.empty { color: #94a3b8; font-size: 13px; }
.match-summary { font-size: 12px; color: #b45309; }
.grid { border-collapse: collapse; font-size: 12px; width: 100%; }
.grid th, .grid td { border: 1px solid #e2e8f0; padding: 6px 10px; text-align: left; }
.grid th { background: #f8fafc; font-weight: 600; }
.mono { font-family: ui-monospace, monospace; }
.badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 600; }
.badge--ok { background: #dcfce7; color: #15803d; }
.badge--none { background: #f1f5f9; color: #64748b; }
.req-input { flex: 1; min-width: 18rem; font-size: 12px; padding: 7px 10px;
  border: 1px solid #cbd5e1; border-radius: 6px; }
.sev-select { font-size: 13px; padding: 6px 8px; border: 1px solid #cbd5e1; border-radius: 6px; }
.sev-bar { display: flex; gap: 8px; flex-wrap: wrap; }
.sev-pill { font-size: 11px; padding: 2px 10px; border-radius: 10px; font-weight: 600; background: #f1f5f9; color: #334155; }
.sev-pill--critical { background: #fee2e2; color: #991b1b; }
.sev-pill--high { background: #ffedd5; color: #9a3412; }
.sev-pill--medium { background: #fef9c3; color: #854d0e; }
.sev-pill--low { background: #dcfce7; color: #166534; }
.sev-pill--unknown { background: #f1f5f9; color: #64748b; }
</style>

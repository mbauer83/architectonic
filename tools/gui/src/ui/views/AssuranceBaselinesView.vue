<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'

interface Baseline {
  sealed_at: string
  notes?: string
  analysis_id?: string
  head_hash?: string
  baseline_id?: string
}

const baselines = ref<Baseline[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const sealing = ref(false)
const sealNotes = ref('')
const sealError = ref<string | null>(null)
const sealSuccess = ref(false)

async function loadBaselines() {
  loading.value = true
  error.value = null
  try {
    const resp = await fetch('/api/assurance/baselines')
    if (resp.status === 423) {
      error.value = 'Store is locked. Unlock the assurance store to view baselines.'
      return
    }
    if (!resp.ok) { error.value = `HTTP ${resp.status}`; return }
    const body = await resp.json() as { baselines: Baseline[] }
    baselines.value = body.baselines ?? []
  } catch (e) {
    error.value = String(e)
  } finally {
    loading.value = false
  }
}

async function handleSeal() {
  sealing.value = true
  sealError.value = null
  sealSuccess.value = false
  try {
    const resp = await fetch('/api/assurance/baselines/seal', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes: sealNotes.value }),
    })
    if (resp.status === 423) { sealError.value = 'Store is locked.'; return }
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({})) as Record<string, unknown>
      sealError.value = typeof body['error'] === 'string' ? body['error'] : `HTTP ${resp.status}`
      return
    }
    sealNotes.value = ''
    sealSuccess.value = true
    await loadBaselines()
  } catch (e) {
    sealError.value = String(e)
  } finally {
    sealing.value = false
  }
}

function formatDate(raw: string): string {
  try { return new Date(raw).toLocaleString() } catch { return raw }
}

onMounted(loadBaselines)
</script>

<template>
  <div class="baselines-view">
    <div class="baselines-header">
      <RouterLink
        to="/assurance"
        class="back-link"
      >
        ← Assurance
      </RouterLink>
      <h1 class="baselines-title">
        Sealed Baselines
      </h1>
      <p class="baselines-subtitle">
        Tamper-evident snapshots of the assurance analysis state. Required before CAST investigations.
      </p>
    </div>

    <!-- Seal form -->
    <div class="seal-form">
      <h2 class="section-title">
        Seal a new baseline
      </h2>
      <textarea
        v-model="sealNotes"
        class="seal-notes"
        rows="2"
        placeholder="Optional notes (e.g. 'Before incident investigation CAST-001')"
        :disabled="sealing"
      />
      <div class="seal-actions">
        <button
          class="btn-seal"
          :disabled="sealing"
          @click="handleSeal"
        >
          {{ sealing ? 'Sealing…' : 'Seal baseline' }}
        </button>
      </div>
      <p
        v-if="sealError"
        class="seal-error"
      >
        {{ sealError }}
      </p>
      <p
        v-if="sealSuccess"
        class="seal-success"
      >
        Baseline sealed.
      </p>
    </div>

    <!-- Loading / error -->
    <div
      v-if="loading"
      class="state-msg"
    >
      Loading…
    </div>
    <div
      v-else-if="error"
      class="state-error"
    >
      {{ error }}
    </div>

    <!-- Baselines list -->
    <div
      v-else-if="baselines.length === 0"
      class="state-msg"
    >
      No baselines sealed yet. Use the form above or call <code>assurance_seal_baseline</code> to create one.
    </div>
    <div
      v-else
      class="baselines-list"
    >
      <h2 class="section-title">
        {{ baselines.length }} baseline{{ baselines.length === 1 ? '' : 's' }}
      </h2>
      <div
        v-for="b in baselines"
        :key="b.baseline_id ?? b.sealed_at"
        class="baseline-card"
      >
        <div class="baseline-card__header">
          <span class="baseline-card__date">{{ formatDate(b.sealed_at) }}</span>
          <span
            v-if="b.analysis_id"
            class="baseline-card__tag"
          >{{ b.analysis_id }}</span>
        </div>
        <p
          v-if="b.notes"
          class="baseline-card__notes"
        >
          {{ b.notes }}
        </p>
        <code
          v-if="b.head_hash"
          class="baseline-card__hash"
        >{{ b.head_hash }}</code>
      </div>
    </div>
  </div>
</template>

<style scoped>
.baselines-view { max-width: 800px; margin: 0 auto; padding: 32px 24px; }
.back-link { font-size: 13px; color: #64748b; display: block; margin-bottom: 16px; }
.baselines-title { font-size: 22px; font-weight: 700; margin: 0 0 6px; }
.baselines-subtitle { color: #64748b; font-size: 14px; margin: 0 0 28px; }
.section-title { font-size: 15px; font-weight: 600; margin: 0 0 12px; }
.seal-form { border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin-bottom: 28px; background: #f8fafc; }
.seal-notes { width: 100%; box-sizing: border-box; font-size: 13px; padding: 8px 10px; border: 1px solid #d1d5db; border-radius: 6px; resize: vertical; }
.seal-actions { margin-top: 10px; }
.btn-seal { padding: 8px 18px; background: #0f172a; color: #fff; border: none; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; }
.btn-seal:hover:not(:disabled) { background: #1e293b; }
.btn-seal:disabled { opacity: 0.5; cursor: default; }
.seal-error { color: #dc2626; font-size: 13px; margin-top: 8px; }
.seal-success { color: #15803d; font-size: 13px; margin-top: 8px; }
.state-msg { color: #64748b; font-size: 14px; padding: 12px 0; }
.state-error { color: #dc2626; font-size: 14px; padding: 12px 0; }
.baselines-list { display: flex; flex-direction: column; gap: 12px; }
.baseline-card { border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 16px; background: #fff; }
.baseline-card__header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.baseline-card__date { font-size: 13px; font-weight: 500; color: #374151; }
.baseline-card__tag { font-size: 11px; background: #dbeafe; color: #1d4ed8; padding: 2px 7px; border-radius: 10px; }
.baseline-card__notes { font-size: 13px; color: #4b5563; margin: 0 0 8px; }
.baseline-card__hash { font-size: 11px; color: #6b7280; background: #f1f5f9; padding: 2px 6px; border-radius: 4px; display: block; word-break: break-all; }
</style>

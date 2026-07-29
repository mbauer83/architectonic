<script setup lang="ts">
/**
 * Ingest an SBOM (and optionally OSV records) for THIS architecture entity.
 *
 * Lives on the entity page because the architecture model is the navigation spine
 * for assurance: the anchor is where an architect already is when they have a bill
 * of materials for it. The submission goes through the same gated, audited,
 * idempotent command as the CLI, MCP and REST surfaces — the browser is another
 * adapter, not a bypass.
 *
 * Rendered only for entity types the BACKEND declares admissible, fetched at
 * runtime so the GUI cannot offer an ingest the API would refuse.
 */
import { computed, ref, watch } from 'vue'
import {
  asText, canAnchorSignals, changedTheStore, describeOutcome, parseSubmission, requestIdFor,
} from './SignalIngestPanel.helpers'

const props = defineProps<{ artifactId: string; entityType?: string }>()
const emit = defineEmits<{ ingested: [] }>()

const admissible = ref<string[]>([])
const open = ref(false)
const bomText = ref('')
const vulnText = ref('')
const busy = ref(false)
const error = ref<string | null>(null)
const outcome = ref<string | null>(null)

const eligible = computed(() => canAnchorSignals(props.entityType, admissible.value))
const canSubmit = computed(() => !busy.value && bomText.value.trim() !== '')

async function loadAdmissible() {
  try {
    const resp = await fetch('/api/assurance/signal-anchor-types')
    if (!resp.ok) return
    const body = await resp.json() as { anchor_types?: string[] }
    admissible.value = body.anchor_types ?? []
  } catch {
    admissible.value = [] // signals unavailable ⇒ no ingest affordance
  }
}

async function submit() {
  const submission = { bomText: bomText.value, vulnText: vulnText.value }
  const parsed = parseSubmission(submission)
  if (parsed.error || !parsed.bom) { error.value = parsed.error ?? 'Parse error'; return }
  busy.value = true
  error.value = null
  outcome.value = null
  try {
    const resp = await fetch('/api/assurance/security-ingest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        anchor_entity_id: props.artifactId,
        bom: parsed.bom,
        vulnerabilities: parsed.vulnerabilities ?? [],
        // Derived from the paste, so a retry replays rather than duplicating.
        request_id: requestIdFor(submission),
        source: 'gui',
      }),
    })
    if (resp.status === 423) { error.value = 'The assurance store is locked.'; return }
    const body = await resp.json().catch(() => ({})) as Record<string, unknown>
    if (resp.status === 403) {
      error.value = asText(body['message'], 'Signal mutations are denied by this deployment.')
      return
    }
    const message = describeOutcome(resp.status, body)
    if (changedTheStore(body)) {
      outcome.value = message
      bomText.value = ''
      vulnText.value = ''
      // The derived-attributes panel and findings view read the active snapshot;
      // they are stale the moment this succeeds.
      emit('ingested')
    } else {
      error.value = message
    }
  } catch (e) {
    error.value = String(e)
  } finally {
    busy.value = false
  }
}

watch(() => props.artifactId, loadAdmissible, { immediate: true })
</script>

<template>
  <section
    v-if="eligible"
    class="signal-ingest"
  >
    <div class="panel-title">
      Security signals
      <button
        class="toggle"
        type="button"
        data-testid="ingest-toggle"
        @click="open = !open"
      >
        {{ open ? 'Cancel' : 'Ingest SBOM…' }}
      </button>
    </div>

    <template v-if="open">
      <p class="hint">
        Paste a CycloneDX SBOM for this element. OSV vulnerability records are
        optional — without them this ingests an inventory-only snapshot. Ingesting
        supersedes this element's previous active snapshot.
      </p>
      <textarea
        v-model="bomText"
        class="json-input"
        rows="8"
        aria-label="CycloneDX SBOM (JSON)"
        placeholder="Paste a CycloneDX SBOM (JSON)…"
        data-testid="ingest-bom"
      />
      <textarea
        v-model="vulnText"
        class="json-input"
        rows="4"
        aria-label="OSV vulnerability records (JSON array, optional)"
        placeholder="Optional: OSV vulnerability records (JSON array)…"
        data-testid="ingest-vulns"
      />
      <div class="actions">
        <span class="idempotency-note">
          Ingesting the same paste twice is safe — the second attempt replays the
          first instead of creating another snapshot.
        </span>
        <button
          class="submit"
          type="button"
          :disabled="!canSubmit"
          data-testid="ingest-submit"
          @click="submit"
        >
          {{ busy ? 'Ingesting…' : 'Ingest' }}
        </button>
      </div>
    </template>

    <p
      v-if="error"
      class="msg msg--error"
      role="alert"
      data-testid="ingest-error"
    >
      {{ error }}
    </p>
    <p
      v-if="outcome"
      class="msg msg--ok"
      role="status"
      data-testid="ingest-outcome"
    >
      {{ outcome }}
    </p>
  </section>
</template>

<style scoped>
.signal-ingest {
  background: #f8fafc; border: 1px solid #e2e8f0; border-left: 4px solid #1e293b;
  border-radius: 6px; padding: 10px 14px; margin-top: 12px;
}
.panel-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 12px; font-weight: 600; color: #374151;
}
.toggle {
  margin-left: auto; font-size: 11px; padding: 2px 8px; cursor: pointer;
  background: #fff; color: #2563eb; border: 1px solid #cbd5e1; border-radius: 4px;
}
.hint { font-size: 11px; color: #64748b; margin: 8px 0; }
.json-input {
  width: 100%; font-family: ui-monospace, monospace; font-size: 11px;
  padding: 7px 9px; border: 1px solid #cbd5e1; border-radius: 6px; margin-bottom: 6px;
}
.actions { display: flex; gap: 8px; align-items: center; }
.idempotency-note { flex: 1; font-size: 10px; color: #64748b; line-height: 1.35; }
.submit {
  font-size: 12px; padding: 6px 14px; border: none; border-radius: 6px;
  background: #2563eb; color: #fff; font-weight: 600; cursor: pointer;
}
.submit:disabled { opacity: 0.5; cursor: default; }
.msg { font-size: 11px; margin: 8px 0 0; padding: 6px 8px; border-radius: 4px; }
.msg--error { background: #fdecea; color: #8a1c12; }
.msg--ok { background: #eef7ee; color: #2c5f2e; }
</style>

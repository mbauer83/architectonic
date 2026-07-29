<script setup lang="ts">
/**
 * Component vulnerabilities for one architecture entity: the findings of its
 * ACTIVE signal snapshot, grouped under the component they affect.
 *
 * Reached primarily from the entity's own detail page — the anchor is where an
 * architect is already standing when they ask "what is wrong with this thing?".
 * Each vulnerability links onward to the entities it affects, so a finding is a
 * starting point for navigation rather than a dead end.
 */
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  emptyMessage, groupByComponent, vulnerabilityKey, vulnerabilityLabel, withheldNote,
  type FindingsPayload,
} from './SecurityFindingsView.helpers'

const route = useRoute()
const anchorId = computed(() => (route.query.anchor as string | undefined) ?? '')

const payload = ref<FindingsPayload | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

const groups = computed(() => groupByComponent(payload.value?.findings ?? []))
const withheld = computed(() => (payload.value ? withheldNote(payload.value) : null))
const empty = computed(() => (payload.value ? emptyMessage(payload.value) : null))

async function load() {
  if (!anchorId.value) { payload.value = null; return }
  loading.value = true
  error.value = null
  try {
    const resp = await fetch(
      `/api/assurance/security-findings?anchor_entity_id=${encodeURIComponent(anchorId.value)}`)
    if (resp.status === 423) { error.value = 'The assurance store is locked.'; return }
    if (!resp.ok) { error.value = `HTTP ${resp.status}`; return }
    payload.value = await resp.json() as FindingsPayload
  } catch (e) {
    error.value = String(e)
  } finally {
    loading.value = false
  }
}

watch(anchorId, load, { immediate: true })
</script>

<template>
  <section class="findings-view">
    <header>
      <h1>Component vulnerabilities</h1>
      <p class="anchor">
        Active signal snapshot for
        <RouterLink :to="`/entity?id=${encodeURIComponent(anchorId)}`">
          <code>{{ anchorId }}</code>
        </RouterLink>
      </p>
    </header>

    <p
      v-if="loading"
      class="status"
    >
      Loading…
    </p>
    <p
      v-else-if="error"
      class="status error"
      role="alert"
    >
      {{ error }}
    </p>

    <template v-else-if="payload">
      <p
        v-if="withheld"
        class="status withheld"
        role="status"
      >
        {{ withheld }}
      </p>
      <p
        v-if="empty"
        class="status empty"
      >
        {{ empty }}
      </p>

      <p
        v-else
        class="summary"
        data-testid="findings-summary"
      >
        {{ payload.count ?? 0 }} finding{{ (payload.count ?? 0) === 1 ? '' : 's' }}
        across {{ groups.length }} component{{ groups.length === 1 ? '' : 's' }}
      </p>

      <article
        v-for="group in groups"
        :key="group.componentPurl || group.componentName"
        class="component"
        data-testid="component-group"
      >
        <h2>
          {{ group.componentName }}
          <span
            class="directness"
            :class="`directness--${group.directness}`"
          >
            {{ group.directness }}
          </span>
        </h2>
        <p class="purl">
          <code>{{ group.componentPurl }}</code>
        </p>

        <table>
          <!-- Every component renders its own table, so with the default
               content-based layout each one sized its columns independently and
               the grids did not line up down the page (a 19-character GHSA id
               shifted Severity ~46px right of a 15-character PYSEC one). Fixed
               layout plus explicit widths gives every group identical geometry. -->
          <colgroup>
            <col>
            <col class="col-severity">
            <col class="col-cvss">
            <col class="col-applicability">
          </colgroup>
          <thead>
            <tr>
              <th scope="col">
                Vulnerability
              </th>
              <th scope="col">
                Severity
              </th>
              <th scope="col">
                CVSS
              </th>
              <th scope="col">
                Applicability
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="finding in group.findings"
              :key="finding.finding_id"
              data-testid="finding-row"
            >
              <td>
                <RouterLink
                  :to="`/assurance/security/vulnerability?id=${encodeURIComponent(vulnerabilityKey(finding))}`"
                  data-testid="vulnerability-link"
                >
                  {{ vulnerabilityLabel(finding) }}
                </RouterLink>
              </td>
              <td>
                <span
                  class="band"
                  :class="`band--${finding.severity_band ?? 'unknown'}`"
                >{{ finding.severity_band ?? 'unknown' }}</span>
              </td>
              <td>{{ finding.cvss_score ?? '—' }}</td>
              <td>{{ finding.applicability ?? 'applicable' }}</td>
            </tr>
          </tbody>
        </table>
      </article>
    </template>
  </section>
</template>

<style scoped>
.findings-view { padding: 1rem 1.25rem; max-width: 68rem; }
header h1 { margin: 0 0 0.25rem; font-size: 1.25rem; }
.anchor { margin: 0 0 1rem; color: var(--muted, #666); font-size: 0.9rem; }
.status { padding: 0.5rem 0.75rem; border-radius: 4px; font-size: 0.9rem; }
.status.error { background: #fdecea; color: #8a1c12; }
.status.withheld { background: #fff6e5; color: #7a5200; }
.status.empty { background: #f3f4f6; color: #444; }
.summary { color: var(--muted, #666); font-size: 0.9rem; margin: 0.5rem 0 1rem; }
.component { border: 1px solid var(--border, #e2e4e8); border-radius: 6px;
  padding: 0.75rem 1rem; margin-bottom: 1rem; }
.component h2 { margin: 0; font-size: 1rem; display: flex; align-items: center; gap: 0.5rem; }
.purl { margin: 0.15rem 0 0.6rem; font-size: 0.8rem; color: var(--muted, #666); }
.directness { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.04em;
  padding: 0.1rem 0.4rem; border-radius: 999px; background: #eef1f5; color: #445; }
.directness--direct { background: #e5efff; color: #1a4a8a; }
.directness--transitive { background: #f1eefe; color: #4b3a8a; }
table { width: 100%; border-collapse: collapse; font-size: 0.9rem;
  table-layout: fixed; }
.col-severity { width: 7.5rem; }
.col-cvss { width: 5rem; }
.col-applicability { width: 9rem; }
/* Fixed layout will not grow for a long id, so wrap instead of overflowing. */
tbody td:first-child { overflow-wrap: anywhere; }
th { text-align: left; font-weight: 600; color: var(--muted, #666);
  border-bottom: 1px solid var(--border, #e2e4e8); padding: 0.3rem 0.4rem; }
td { padding: 0.3rem 0.4rem; border-bottom: 1px solid var(--border-soft, #f0f1f4); }
.band { font-size: 0.75rem; padding: 0.1rem 0.45rem; border-radius: 999px; background: #eef1f5; }
.band--critical { background: #fde0dd; color: #8a1020; }
.band--high { background: #fdecea; color: #8a1c12; }
.band--medium { background: #fff6e5; color: #7a5200; }
.band--low { background: #eef7ee; color: #2c5f2e; }
</style>

<script setup lang="ts">
/**
 * Which architecture entities carry an active security-signal snapshot, and how much each holds.
 *
 * The way in when you do not already have an anchor. A finding belongs to an entity, so the read that
 * answers "what is wrong with this thing?" is a subresource of the entity and needs its id; the
 * unanchored address that used to answer "every finding" is retired. This lists the anchors instead,
 * which is the honest shape — and it is what the nav's "Security findings" entry now reaches.
 *
 * Before this existed that entry mounted the per-anchor view with no anchor, which rendered its
 * header — *Active signal snapshot for* — followed by an empty link, and nothing else.
 */
import { computed, onMounted, ref } from 'vue'
import {
  decodeSecuritySignalStats,
  type AssessedEntity, type SecuritySignalStats,
} from '../../domain/schemas/assurance-security'
import { indexState } from './SecurityFindingsIndexView.helpers'
import { assuranceSecurityFindingsRoute } from '../router/artifactRoutes'

const stats = ref<SecuritySignalStats | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

const anchors = computed<readonly AssessedEntity[]>(() => stats.value?.assessed_entities ?? [])
const state = computed(() => (stats.value ? indexState(stats.value) : null))

async function load() {
  loading.value = true
  error.value = null
  try {
    const resp = await fetch('/api/assurance/security-stats')
    if (resp.status === 423) { error.value = 'The assurance store is locked.'; return }
    if (!resp.ok) { error.value = `HTTP ${resp.status}`; return }
    stats.value = decodeSecuritySignalStats(await resp.json())
  } catch (e) {
    error.value = String(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="findings-index">
    <header>
      <h1>Security findings</h1>
      <p class="lede">
        Entities with an active signal snapshot. Open one to see the vulnerabilities of the
        components it depends on.
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

    <template v-else>
      <!-- Which of the four states this read puts the page in is decided by `indexState`, so the
           distinction between "nothing ingested" and "snapshots that assess nothing" is testable
           without a browser: they are different situations with different next steps. -->
      <p
        v-if="state?.kind === 'limited'"
        class="status withheld"
        role="status"
      >
        {{ state.reason }}
      </p>
      <p
        v-else-if="state?.kind === 'no-snapshots'"
        class="status empty"
        data-testid="no-snapshots"
      >
        No security signals have been ingested. Run
        <code>assurance_ingest_security_signals</code> against an entity, or
        <code>arch-assurance seed --with-signals</code> to load the ones this repository declares.
      </p>
      <p
        v-else-if="state?.kind === 'no-assessed-entities'"
        class="status empty"
        data-testid="no-assessed-entities"
      >
        {{ state.snapshots }} snapshot{{ state.snapshots === 1 ? '' : 's' }} recorded, none of them
        active against an entity.
      </p>

      <table v-else>
        <thead>
          <tr>
            <th scope="col">
              Entity
            </th>
            <th scope="col">
              Components
            </th>
            <th scope="col">
              Findings
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="anchor in anchors"
            :key="anchor.snapshot_id"
            data-testid="assessed-entity-row"
          >
            <td>
              <RouterLink
                :to="assuranceSecurityFindingsRoute(anchor.entity_id)"
                data-testid="assessed-entity-link"
              >
                <code>{{ anchor.entity_id }}</code>
              </RouterLink>
            </td>
            <td>{{ anchor.bom_component_count }}</td>
            <td>{{ anchor.finding_count }}</td>
          </tr>
        </tbody>
      </table>
    </template>
  </section>
</template>

<style scoped>
.findings-index { padding: 1rem 1.25rem; max-width: 68rem; }
header h1 { margin: 0 0 0.25rem; font-size: 1.25rem; }
.lede { margin: 0 0 1rem; color: var(--muted, #666); font-size: 0.9rem; }
.status { padding: 0.5rem 0.75rem; border-radius: 4px; font-size: 0.9rem; }
.status.error { background: #fdecea; color: #8a1c12; }
.status.withheld { background: #fff6e5; color: #7a5200; }
.status.empty { background: #f3f4f6; color: #444; }
.status code { background: #e8eaee; border-radius: 3px; padding: 0 0.25rem; }
table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
th { text-align: left; font-weight: 600; color: var(--muted, #666);
  border-bottom: 1px solid var(--border, #e2e4e8); padding: 0.3rem 0.4rem; }
td { padding: 0.3rem 0.4rem; border-bottom: 1px solid var(--border-soft, #f0f1f4); }
td:not(:first-child), th:not(:first-child) { width: 7rem; text-align: right; }
</style>

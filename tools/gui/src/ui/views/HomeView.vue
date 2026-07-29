<script setup lang="ts">
import { inject, onMounted, computed } from 'vue'
import { RouterLink } from 'vue-router'
import { modelServiceKey } from '../keys'
import { useQuery } from '../composables/useQuery'
import type { Stats, EntityList } from '../../domain'
import type { RepoError } from '../../ports/ModelRepository'
import { domainOptionsForDomains } from '../lib/domains'
import PinnedViewpointsSection from '../components/PinnedViewpointsSection.vue'

const svc = inject(modelServiceKey)!
const statsState = useQuery<Stats, RepoError>()
const engagementListState = useQuery<EntityList, RepoError>()
const globalListState = useQuery<EntityList, RepoError>()

onMounted(() => {
  statsState.run(svc.getStats())
  engagementListState.run(svc.listEntities({ scope: 'engagement', limit: 1 }))
  globalListState.run(svc.listEntities({ scope: 'global', limit: 1 }))
})

const engCount = computed(() => engagementListState.data.value?.total ?? null)
const gloCount = computed(() => globalListState.data.value?.total ?? null)
const hasGlobal = computed(() => gloCount.value !== null && gloCount.value > 0)
const activeDomainOptions = computed(() =>
  domainOptionsForDomains(Object.keys(statsState.data.value?.entities_by_domain ?? {})),
)
</script>

<template>
  <div>
    <h1 class="page-title">
      Model Overview
    </h1>

    <div
      v-if="statsState.loading.value"
      class="state-msg"
    >
      Loading…
    </div>
    <div
      v-else-if="statsState.errorMessage.value"
      class="state-msg state-msg--error"
    >
      {{ statsState.errorMessage.value }}
    </div>

    <template v-else-if="statsState.data.value">
      <!-- Two-repo summary cards -->
      <div class="repo-cards">
        <div class="repo-card repo-card--engagement">
          <div class="repo-card__header">
            <span class="repo-label">Engagement</span>
          </div>
          <div class="repo-stats">
            <div class="repo-stat">
              <span class="stat-num">{{ engCount ?? statsState.data.value.entities }}</span>
              <span class="stat-label">Entities</span>
            </div>
            <div class="repo-stat">
              <span class="stat-num">{{ statsState.data.value.connections }}</span>
              <span class="stat-label">Connections</span>
            </div>
            <div class="repo-stat">
              <span class="stat-num">{{ statsState.data.value.diagrams }}</span>
              <span class="stat-label">Diagrams</span>
            </div>
          </div>
        </div>

        <div
          class="repo-card repo-card--global"
          :class="{ 'repo-card--empty': !hasGlobal }"
        >
          <div class="repo-card__header">
            <span class="repo-label repo-label--global">Enterprise</span>
          </div>
          <div class="repo-stats">
            <div class="repo-stat">
              <span class="stat-num">{{ gloCount ?? '–' }}</span>
              <span class="stat-label">Entities</span>
            </div>
          </div>
          <p
            v-if="!hasGlobal"
            class="repo-empty"
          >
            No enterprise entities yet. Promote engagement entities to populate the enterprise repository.
          </p>
        </div>
      </div>

      <!-- Domain breakdown for engagement repo -->
      <PinnedViewpointsSection />

      <h2 class="section-title">
        Engagement — Entities by Domain
      </h2>
      <div class="domain-grid">
        <RouterLink
          v-for="d in activeDomainOptions"
          :key="d.key"
          :to="{ path: '/entities', query: { domain: d.key } }"
          class="card card--domain"
          :class="`domain--${d.key}`"
        >
          <span class="domain-name">{{ d.label }}</span>
          <span class="domain-count">{{ statsState.data.value.entities_by_domain[d.key] ?? 0 }}</span>
        </RouterLink>
      </div>

      <h2 class="section-title">
        Connections by Type
      </h2>
      <table class="conn-table">
        <tbody>
          <tr
            v-for="(count, type) in statsState.data.value.connections_by_type"
            :key="type"
          >
            <td class="conn-type">
              {{ type }}
            </td>
            <td class="conn-count">
              {{ count }}
            </td>
          </tr>
        </tbody>
      </table>
    </template>
  </div>
</template>

<style scoped>
.page-title { font-size: 22px; font-weight: 600; margin-bottom: 20px; }
.section-title { font-size: 16px; font-weight: 600; margin: 28px 0 12px; color: #374151; }
.state-msg { color: #6b7280; padding: 12px 0; }
.state-msg--error { color: #dc2626; }

/* ── Two-repo cards ──────────────────────────────────────────── */
.repo-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 28px;
}
@media (max-width: 640px) { .repo-cards { grid-template-columns: 1fr; } }

.repo-card {
  background: white;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.repo-card--global { border-color: #fde68a; background: #fffdf5; }
.repo-card--empty { opacity: .85; }

.repo-card__header { display: flex; align-items: center; gap: 10px; }

.repo-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .07em;
  color: #475569;
}
.repo-label--global { color: #92400e; }

.repo-stats { display: flex; gap: 20px; flex-wrap: wrap; }
.repo-stat { display: flex; flex-direction: column; }
.stat-num { font-size: 26px; font-weight: 700; color: #1e293b; line-height: 1.1; }
.stat-label { font-size: 11px; color: #6b7280; text-transform: uppercase; letter-spacing: .04em; }

.repo-empty { font-size: 13px; color: #92400e; font-style: italic; }

/* ── Domain grid ─────────────────────────────────────────────── */
.domain-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
}
.card {
  background: white;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  padding: 16px 20px;
}
.card--domain {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-left: 4px solid;
  padding: 12px 16px;
  color: inherit;
}
.card--domain:hover { text-decoration: none; box-shadow: 0 2px 8px rgba(0,0,0,.08); }
.domain-name { font-weight: 500; font-size: 13px; }
.domain-count { font-size: 20px; font-weight: 700; }

.domain--motivation  { border-left-color: #d8c1e4; }
.domain--strategy    { border-left-color: #efbd5d; }
.domain--business    { border-left-color: #f4de7f; }
.domain--common      { border-left-color: #e8e5d3; }
.domain--application { border-left-color: #b6d7e1; }
.domain--technology  { border-left-color: #c3e1b4; }

.conn-table { border-collapse: collapse; }
.conn-type { padding: 4px 16px 4px 0; font-family: monospace; font-size: 12px; color: #374151; }
.conn-count { padding: 4px 8px; font-weight: 600; color: #1e293b; }
</style>
